"""一文档一树 DSL 解析（tree/nodes/root + 槽位引用，契约 §12/§14）。

行为树文档为单树结构：``tree <名>`` + 可选 ``inputs``/``outputs`` + 可选
全局配置 + ``nodes``（节点对象池平铺）+ ``root: <id>``。本模块把该结构
解析为 IR 树（每节点经 M2 节点解析器识别类型），从 ``root`` 沿 ``slots``
构建主树；未被任何槽位引用的节点为游离树。

产出结构供展开/校验（expand/checks）复用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from webops.parser.document import IRNode, _empty_ir, _loc, _parse_node
from webops.parser.models import Loc
from webops.parser.yamlio import normalize_document

_NODE_TYPES = frozenset(
    {"Root", "Step", "Sequence", "IfThenElse", "Branch", "Retry", "LoopUntil", "ref"}
)


@dataclass
class OneDocResult:
    """一文档一树解析结果。

    :param decl_inputs: 文档级入参声明（名→类型）。
    :param decl_outputs: 文档级出参名列表。
    :param config: 全局配置覆盖（timeout/retry/browser）。
    :param main_tree: 主树 IR（从 root 沿 slots 递归构建；无 Root 时为 None）。
    :param free_trees: 游离树 IR 列表（未被任何 slots 引用的节点为根）。
    :param issues: 解析期校验问题。
    """

    decl_inputs: dict[str, str] = field(default_factory=dict)
    decl_outputs: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    main_tree: IRNode | None = None
    free_trees: list[IRNode] = field(default_factory=list)
    issues: list = field(default_factory=list)

    def checks_ok(self) -> bool:
        return not self.issues


def parse_document(doc) -> OneDocResult:
    """解析一文档一树 DSL。

    :param doc: DocumentSource（id 为文档名）。
    """
    result = OneDocResult()
    issues: list = result.issues
    doc_id = doc.id
    raw = normalize_document(doc.data)

    if "tree" in raw:
        tree_name = raw["tree"]
        if tree_name != doc_id:
            issues.append(
                _issue(
                    doc_id,
                    "structure",
                    "name_mismatch",
                    f"tree 名 '{tree_name}' 与文档名 '{doc_id}' 不一致",
                )
            )
    else:
        issues.append(
            _issue(doc_id, "structure", "missing_tree", "文档缺少 tree 顶层键")
        )

    nodes_raw = raw.get("nodes")
    if not isinstance(nodes_raw, dict) or not nodes_raw:
        issues.append(_issue(doc_id, "structure", "missing_nodes", "文档缺少 nodes 节点池"))
        return result
    root_id = raw.get("root")
    if not isinstance(root_id, str) or root_id not in nodes_raw:
        issues.append(
            _issue(doc_id, "structure", "invalid_root", f"root 引用 '{root_id}' 不在 nodes 中")
        )
        return result
    root_body = nodes_raw[root_id]
    if not isinstance(root_body, dict) or root_body.get("type") != "Root":
        issues.append(
            _issue(
                doc_id,
                "structure",
                "invalid_root",
                f"root 引用 '{root_id}' 必须指向 type:Root 节点",
            )
        )
        return result

    decl_inputs = raw.get("inputs", {})
    if isinstance(decl_inputs, dict):
        from webops.schema.types import TYPE_REGISTRY

        for name, typ in decl_inputs.items():
            if typ not in TYPE_REGISTRY:
                issues.append(
                    _issue(
                        doc_id,
                        "structure",
                        "invalid_decl",
                        f"入参 '{name}' 类型 '{typ}' 未登记（支持: {sorted(TYPE_REGISTRY)}）",
                    )
                )
        result.decl_inputs = dict(decl_inputs)
    decl_outputs = raw.get("outputs", [])
    if isinstance(decl_outputs, list):
        result.decl_outputs = list(decl_outputs)
    config = {k: v for k, v in raw.items() if k in ("timeout", "retry", "browser")}
    result.config = config

    # 解析每个节点 → (IRNode, 槽位子 id 列表)，按 id 建表
    nodes: dict[str, tuple[IRNode, list[str]]] = {}
    for nid, body in nodes_raw.items():
        if not isinstance(body, dict):
            issues.append(_issue(doc_id, "structure", "invalid_node", f"节点 '{nid}' 不是映射"))
            continue
        ntype = body.get("type")
        if ntype not in _NODE_TYPES:
            issues.append(
                _issue(doc_id, "structure", "unknown_node", f"节点 '{nid}' 类型 '{ntype}' 未知")
            )
            continue
        loc = _loc(doc_id, f"nodes/{nid}")
        node = _build_ir_node(doc_id, nid, ntype, body, loc, issues)
        slots = body.get("slots", {})
        child_ids: list[str] = []
        if isinstance(slots, dict):
            child_ids = [v for v in slots.values() if isinstance(v, str)]
        nodes[nid] = (node, child_ids)

    # 引用关系：子 id 必须存在；统计被引用次数；检测重复引用
    referenced: set[str] = set()
    parent_of: dict[str, str] = {}
    for nid, (_, child_ids) in nodes.items():
        for cid in child_ids:
            if cid not in nodes:
                issues.append(
                    _issue(
                        doc_id,
                        "structure",
                        "orphan_slot",
                        f"节点 '{nid}' 槽位引用不存在的节点 '{cid}'",
                    )
                )
            else:
                if cid in parent_of:
                    issues.append(
                        _issue(
                            doc_id,
                            "structure",
                            "duplicate_reference",
                            f"节点 '{cid}' 被多个槽位引用（{parent_of[cid]} 与 {nid}），破坏纯树结构",
                        )
                    )
                parent_of[cid] = nid
                referenced.add(cid)

    # 无环检测：从 root 与每个游离根 DFS，遇环报错
    child_map = {nid: child_ids for nid, (_, child_ids) in nodes.items()}
    visiting: set[str] = set()
    visited: set[str] = set()

    def detect_cycle(start: str) -> bool:
        if start in visited:
            return False
        stack = [(start, iter(child_map.get(start, [])))]
        visiting = {start}
        while stack:
            node, it = stack[-1]
            advanced = False
            for c in it:
                if c not in child_map:
                    continue
                if c in visiting:
                    return True
                if c not in visited:
                    visiting.add(c)
                    stack.append((c, iter(child_map.get(c, []))))
                    advanced = True
                    break
            if not advanced:
                visiting.discard(node)
                visited.add(node)
                stack.pop()
        return False

    cycle_starts = [root_id] if root_id in nodes else []
    cycle_starts.extend(
        nid for nid in nodes if nid not in referenced and nid != root_id
    )
    for start in cycle_starts:
        if detect_cycle(start):
            issues.append(
                _issue(doc_id, "structure", "cycle", f"节点 '{start}' 的槽位引用存在循环")
            )

    # 构建 IR 树：把 slot 子节点挂到父节点（子节点的 IR 由 nodes 提供）
    def build(node: IRNode, nid: str, seen: frozenset[str] = frozenset()) -> IRNode:
        if nid in seen:  # 环保护（校验已报 cycle，构建时避免递归）
            return node
        _, child_ids = nodes[nid]
        children = [
            build(nodes[c][0], c, seen | {nid}) for c in child_ids if c in nodes
        ]
        if node.kind in ("Sequence", "Root"):
            node = _with_children(node, children)
        return node

    main_node, _ = nodes.get(root_id, (None, []))
    if main_node is not None:
        result.main_tree = build(main_node, root_id)
    # 游离树：未被引用的节点为游离根，各自构建
    for nid, (node, _) in nodes.items():
        if nid in referenced or nid == root_id:
            continue
        result.free_trees.append(build(node, nid))

    return result


def _build_ir_node(
    doc_id: str, nid: str, ntype: str, body: dict, loc: Loc, issues: list
) -> IRNode:
    """按节点类型解析单个节点为 IRNode。

    容器类型（Root/Sequence）直接建空容器，子节点由 slots 递归挂载；
    叶子/复合类型经 M2 节点解析器识别字段。
    """
    if ntype == "Root":
        return _empty_ir("Root", loc)
    if ntype == "Sequence":
        return _empty_ir("Sequence", loc)
    if ntype == "ref":
        target = body.get("target")
        args = body.get("args", [])
        returns = body.get("returns", {})
        return _ref_ir(doc_id, nid, target, args, returns, loc, issues)
    # 其他类型：把节点字段（不含 type/name/slots/id）作为节点内容
    fields = {k: v for k, v in body.items() if k not in ("type", "name", "slots", "id")}
    return _parse_node(doc_id, f"nodes/{nid}", ntype, fields, issues)


def _ref_ir(
    doc_id: str,
    nid: str,
    target: object,
    args: object,
    returns: object,
    loc: Loc,
    issues: list,
) -> IRNode:
    """构建 ref IRNode：target=文档名单段；args=列表；returns=字典。"""
    if not isinstance(target, str) or not target.strip():
        issues.append(
            _issue(doc_id, "ref", "bad_syntax", f"ref 节点 '{nid}' 缺少 target 文档名")
        )
        return _empty_ir("ref", loc)
    args_pairs: list[tuple[str, str]] = []
    if isinstance(args, list):
        for item in args:
            args_pairs.append((str(item), str(item)))
    returns_pairs: list[tuple[str, str]] = []
    if isinstance(returns, dict):
        for k, v in returns.items():
            returns_pairs.append((str(k), str(v)))
    return IRNode(
        kind="ref",
        ref_target=str(target).strip(),
        args=tuple(args_pairs),
        returns=tuple(returns_pairs),
        loc=loc,
    )


def _with_children(node: IRNode, children: list[IRNode]) -> IRNode:
    """给容器节点挂子节点（Sequence/Root 用 children 字段）。"""
    return IRNode(
        kind=node.kind,
        loc=node.loc,
        description=node.description,
        css_hint=node.css_hint,
        target=node.target,
        predicate=node.predicate,
        children=tuple(children),
        branches=node.branches,
        condition=node.condition,
        action=node.action,
        until=node.until,
        body=node.body,
        max=node.max,
        mode=node.mode,
        ref_target=node.ref_target,
        args=node.args,
        returns=node.returns,
    )


def _issue(doc_id: str, prefix: str, code: str, message: str):
    from webops.parser.models import make_issue

    return make_issue(prefix, code, message, _loc(doc_id, "$"))
