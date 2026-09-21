"""一文档一树 DSL 解析（统一槽位模型，契约 §12/§14）。

行为树文档为单树结构：``tree <名>`` + 可选 ``inputs``/``outputs`` + 可选
全局配置 + ``nodes``（节点对象池平铺）+ ``root: <id>``。**统一槽位模型**：
节点间一切动作关联经语义命名槽位字段引用子树根节点 id：

- Root.body / Sequence.actions / Step.action / IfThenElse.then+else /
  Branch.action+branches[].action / Retry.body / LoopUntil.action
- Action 为真正叶子（description）；Condition 为概念性节点，内嵌为字段
  （Step.expect / IfThenElse.if / Branch.branches[].when / LoopUntil.until）

本模块把该结构解析为 IR 树（每节点经 M2 节点解析器识别类型），从
``root`` 沿槽位字段构建主树；未被任何槽位引用的节点为游离树。

产出结构供展开/校验（expand/checks）复用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from autobranch.parser.document import (
    IRBranch,
    IRNode,
    _empty_ir,
    _loc,
)
from autobranch.parser.models import Loc, make_issue
from autobranch.parser.yamlio import normalize_document

_NODE_TYPES = frozenset(
    {
        "Action",
        "Step",
        "Root",
        "Sequence",
        "IfThenElse",
        "Branch",
        "Retry",
        "LoopUntil",
        "ref",
        "FunctionCall",
    }
)

#: 槽位字段定义（按类型）：字段名 → 挂载形态（single=单子树、list=多子树、branch=分支）。
#: 挂载目标见 ``_attach_children``。
_SLOT_DEFS: dict[str, list[tuple[str, str]]] = {
    "Root": [("body", "single")],
    "Sequence": [("actions", "list")],
    "Step": [("action", "single")],
    "IfThenElse": [("then", "single"), ("else", "single")],
    "Branch": [("action", "single"), ("branches", "branch")],
    "Retry": [("body", "single")],
    "LoopUntil": [("action", "single")],
}


@dataclass
class _Slot:
    """一个节点的槽位引用：字段 → 子 id 列表（+ 分支 when 元数据）。"""

    field: str
    child_ids: list[str]
    metas: list = field(default_factory=list)


@dataclass
class OneDocResult:
    """一文档一树解析结果。

    :param decl_inputs: 文档级入参声明（名→类型）。
    :param decl_outputs: 文档级出参名列表。
    :param config: 全局配置覆盖（timeout/retry/browser）。
    :param main_tree: 主树 IR（从 root 沿槽位递归构建；无 Root 时为 None）。
    :param free_trees: 游离树 IR 列表（未被任何槽位引用的节点为根）。
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


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _cond(
    desc: object,
    doc_id: str,
    path: str,
    issues: list,
    code: str = "",
    message: str = "",
) -> IRNode:
    """把条件字段描述解析为 Condition IRNode（缺失按必填报错）。"""
    loc = _loc(doc_id, path)
    if not isinstance(desc, str) or not desc.strip():
        if code:
            issues.append(make_issue("verify", code, message, loc))
        return _empty_ir("Condition", loc)
    return IRNode(kind="Condition", description=desc.strip(), loc=loc)


def _parse_max(value: object, doc_id: str, path: str, issues: list) -> int | None:
    """循环上界（缺失/非法 → 校验问题）。"""
    loc = _loc(doc_id, path)
    if value is None:
        issues.append(
            make_issue(
                "repeat",
                "max_missing",
                f"循环缺少上界 'max'（防死循环安全闸，位于 {_path(doc_id, path)}）",
                loc,
            )
        )
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.isdigit():
            return int(value)
        issues.append(
            make_issue(
                "repeat",
                "max_not_int",
                f"循环上界 'max' 必须是正整数（当前: {value!r}，位于 {_path(doc_id, path)}）",
                loc,
            )
        )
        return None
    if value < 1:
        issues.append(
            make_issue(
                "repeat",
                "max_not_int",
                f"循环上界 'max' 必须 >= 1（当前: {value}，位于 {_path(doc_id, path)}）",
                loc,
            )
        )
    return value


def _path(doc_id: str, path: str) -> str:
    return f"{doc_id}/{path}"


def parse_document(doc, resolver=None) -> OneDocResult:
    """解析一文档一树 DSL。

    :param doc: DocumentSource（id 为文档名）。
    :param resolver: 跨文档引用解析器（可选，ref 参数对齐/跨文档环校验用）。
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
        issues.append(_issue(doc_id, "structure", "missing_tree", "文档缺少 tree 顶层键"))

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
        from autobranch.schema.types import TYPE_REGISTRY

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

    # 解析每个节点 → (IRNode, 槽位引用列表)，按 id 建表
    nodes: dict[str, tuple[IRNode, list[_Slot]]] = {}
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
        node, slots = _build_ir_node(doc_id, nid, ntype, body, loc, issues)
        nodes[nid] = (node, slots)

    # 引用关系：子 id 必须存在；统计被引用次数；检测重复引用
    child_ids_of: dict[str, list[str]] = {}
    referenced: set[str] = set()
    parent_of: dict[str, str] = {}
    for nid, (_, slots) in nodes.items():
        ids: list[str] = []
        for s in slots:
            for cid in s.child_ids:
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
                                f"节点 '{cid}' 被多个槽位引用"
                                f"（{parent_of[cid]} 与 {nid}），破坏纯树结构",
                            )
                        )
                    parent_of[cid] = nid
                    referenced.add(cid)
                    ids.append(cid)
        child_ids_of[nid] = ids

    # 无环检测：从 root 与每个游离根 DFS，遇环报错
    visited: set[str] = set()

    def detect_cycle(start: str) -> bool:
        if start in visited:
            return False
        stack = [(start, iter(child_ids_of.get(start, [])))]
        visiting = {start}
        while stack:
            node, it = stack[-1]
            advanced = False
            for c in it:
                if c not in child_ids_of:
                    continue
                if c in visiting:
                    return True
                if c not in visited:
                    visiting.add(c)
                    stack.append((c, iter(child_ids_of.get(c, []))))
                    advanced = True
                    break
            if not advanced:
                visiting.discard(node)
                visited.add(node)
                stack.pop()
        return False

    cycle_starts = [root_id] if root_id in nodes else []
    cycle_starts.extend(nid for nid in nodes if nid not in referenced and nid != root_id)
    for start in cycle_starts:
        if detect_cycle(start):
            issues.append(
                _issue(doc_id, "structure", "cycle", f"节点 '{start}' 的槽位引用存在循环")
            )

    # 构建 IR 树：把槽位子节点挂到父节点（子节点的 IR 由 nodes 提供）
    def build(nid: str, seen: frozenset[str] = frozenset()) -> IRNode | None:
        entry = nodes.get(nid)
        if entry is None or nid in seen:  # 环保护（校验已报 cycle，构建时避免递归）
            return None
        node, slots = entry
        child_map: dict[str, list[tuple[IRNode, object]]] = {}
        for s in slots:
            built: list[tuple[IRNode, object]] = []
            for i, cid in enumerate(s.child_ids):
                child_ir = build(cid, seen | {nid})
                if child_ir is not None:
                    meta = s.metas[i] if i < len(s.metas) else None
                    built.append((child_ir, meta))
            child_map[s.field] = built
        return _attach_children(node, slots, child_map)

    if root_id in nodes:
        result.main_tree = build(root_id)
    # 游离树：未被引用的节点为游离根，各自构建
    for nid in nodes:
        if nid in referenced or nid == root_id:
            continue
        tree = build(nid)
        if tree is not None:
            result.free_trees.append(tree)

    if resolver is not None:
        _check_ref_params(doc_id, nodes, resolver, issues)

    return result


def _attach_children(
    node: IRNode, slots: list[_Slot], child_map: dict[str, list[tuple[IRNode, object]]]
) -> IRNode:
    """按节点类型把槽位子树挂到 IRNode 对应字段。"""
    kind = node.kind
    if kind in ("Root", "Sequence"):
        children: list[IRNode] = []
        for s in slots:
            children.extend(ir for ir, _ in child_map.get(s.field, []))
        return _with_children(node, children)
    if kind == "Step":
        kids = child_map.get("action", [])
        return _set(node, action=kids[0][0] if kids else None)
    if kind == "IfThenElse":
        then = child_map.get("then", [])
        els = child_map.get("else", [])
        then_ir = then[0][0] if then else None
        else_ir = els[0][0] if els else None
        return _with_children(node, [i for i in (then_ir, else_ir) if i is not None])
    if kind == "Branch":
        act = child_map.get("action", [])
        branches: list[IRBranch] = []
        for target, meta in child_map.get("branches", []):
            when_desc = meta if isinstance(meta, str) else None
            when_ir = (
                IRNode(kind="Condition", description=when_desc, loc=node.loc)
                if when_desc
                else None
            )
            branches.append(IRBranch(when=when_ir, target=target))
        return _set(node, action=act[0][0] if act else None, branches=tuple(branches))
    if kind == "Retry":
        kids = child_map.get("body", [])
        return _set(node, body=kids[0][0] if kids else None)
    if kind == "LoopUntil":
        kids = child_map.get("action", [])
        return _set(node, action=kids[0][0] if kids else None)
    return node


def _build_ir_node(
    doc_id: str, nid: str, ntype: str, body: dict, loc: Loc, issues: list
) -> tuple[IRNode, list[_Slot]]:
    """按节点类型解析单个节点：构造 IRNode（标量字段）+ 槽位引用。"""
    path = f"nodes/{nid}"
    if ntype == "Action":
        desc = body.get("description")
        if not isinstance(desc, str) or not desc.strip():
            issues.append(
                _issue(
                    doc_id,
                    "structure",
                    "missing_field",
                    f"Action 缺少必需字段 'description'（位于 {_path(doc_id, path)}）",
                )
            )
        return IRNode(kind="Action", description=(desc or "").strip(), loc=loc), []
    if ntype == "ref":
        return _ref_ir(doc_id, nid, body, loc, issues), []
    if ntype == "FunctionCall":
        return _function_call_ir(doc_id, nid, body, loc, issues), []
    if ntype == "Root":
        return IRNode(kind="Root", loc=loc), [_slot("body", _str_or_none(body.get("body")))]
    if ntype == "Sequence":
        actions = body.get("actions", [])
        ids = [a for a in actions if isinstance(a, str)] if isinstance(actions, list) else []
        if isinstance(actions, list) and any(not isinstance(a, str) for a in actions):
            issues.append(
                _issue(
                    doc_id,
                    "structure",
                    "invalid_value",
                    f"Sequence 的 actions 必须全部是节点 id（位于 {_path(doc_id, path)}）",
                )
            )
        return IRNode(kind="Sequence", loc=loc), [_Slot("actions", ids, [])]
    if ntype == "Step":
        expect = body.get("expect")
        if not isinstance(expect, str) or not expect.strip():
            issues.append(
                _issue(
                    doc_id,
                    "verify",
                    "missing_condition",
                    f"Step 缺少验证条件 'expect'（每步必须有验证条件，位于 {_path(doc_id, path)}）",
                )
            )
        node = IRNode(kind="Step", condition=_cond(expect, doc_id, path, issues), loc=loc)
        return node, [_slot("action", _str_or_none(body.get("action")))]
    if ntype == "IfThenElse":
        cond = body.get("if")
        if not isinstance(cond, str) or not cond.strip():
            issues.append(
                _issue(
                    doc_id,
                    "verify",
                    "missing_condition",
                    f"IfThenElse 缺少判断条件 'if'（位于 {_path(doc_id, path)}）",
                )
            )
        node = IRNode(kind="IfThenElse", condition=_cond(cond, doc_id, path, issues), loc=loc)
        return node, [
            _slot("then", _str_or_none(body.get("then"))),
            _slot("else", _str_or_none(body.get("else"))),
        ]
    if ntype == "Retry":
        mx = _parse_max(body.get("max"), doc_id, path, issues)
        if body.get("body") is None:
            issues.append(
                _issue(
                    doc_id,
                    "structure",
                    "missing_field",
                    f"Retry 缺少必需字段 'body'（位于 {_path(doc_id, path)}）",
                )
            )
        return (
            IRNode(kind="Retry", max=mx, loc=loc),
            [_slot("body", _str_or_none(body.get("body")))],
        )
    if ntype == "LoopUntil":
        until = body.get("until")
        if not isinstance(until, str) or not until.strip():
            issues.append(
                _issue(
                    doc_id,
                    "verify",
                    "missing_condition",
                    f"LoopUntil 缺少终止条件 'until'（位于 {_path(doc_id, path)}）",
                )
            )
        mx = _parse_max(body.get("max"), doc_id, path, issues)
        node = IRNode(
            kind="LoopUntil", until=_cond(until, doc_id, path, issues), max=mx, loc=loc
        )
        return node, [_slot("action", _str_or_none(body.get("action")))]
    if ntype == "Branch":
        node = IRNode(kind="Branch", loc=loc)
        branches = body.get("branches", [])
        branch_ids: list[str] = []
        metas: list = []
        if not isinstance(branches, list):
            issues.append(
                _issue(
                    doc_id,
                    "structure",
                    "invalid_value",
                    f"Branch 的 branches 必须是列表（位于 {_path(doc_id, path)}）",
                )
            )
        else:
            for i, item in enumerate(branches):
                if not isinstance(item, dict):
                    issues.append(
                        _issue(
                            doc_id,
                            "structure",
                            "invalid_node",
                            f"Branch 第 {i} 项必须是分支映射"
                            f"（位于 {_path(doc_id, f'{path}/{i}')}）",
                        )
                    )
                    continue
                if "otherwise" in item:
                    act_id = _str_or_none(item.get("otherwise"))
                    if act_id is None:
                        issues.append(
                            _issue(
                                doc_id,
                                "structure",
                                "invalid_node",
                                f"Branch 第 {i} 项 otherwise 缺少槽位引用"
                                f"（位于 {_path(doc_id, f'{path}/{i}')}）",
                            )
                        )
                        continue
                    metas.append(None)
                    branch_ids.append(act_id)
                elif "when" in item:
                    act_id = _str_or_none(item.get("action"))
                    if act_id is None:
                        issues.append(
                            _issue(
                                doc_id,
                                "structure",
                                "invalid_node",
                                f"Branch 第 {i} 项缺少 'action' 槽位引用"
                                f"（位于 {_path(doc_id, f'{path}/{i}')}）",
                            )
                        )
                        continue
                    when = item.get("when")
                    if not isinstance(when, str) or not when.strip():
                        issues.append(
                            _issue(
                                doc_id,
                                "verify",
                                "missing_condition",
                                f"Branch 第 {i} 项缺少分支条件 'when'"
                                f"（位于 {_path(doc_id, f'{path}/{i}')}）",
                            )
                        )
                    metas.append((when or "").strip() if isinstance(when, str) else "")
                    branch_ids.append(act_id)
                else:
                    issues.append(
                        _issue(
                            doc_id,
                            "structure",
                            "invalid_node",
                            f"Branch 第 {i} 项缺少 when/otherwise"
                            f"（位于 {_path(doc_id, f'{path}/{i}')}）",
                        )
                    )
        if not branch_ids:
            issues.append(
                _issue(
                    doc_id,
                    "structure",
                    "missing_field",
                    f"Branch 缺少分支 'branches'"
                    f"（必须有 when/otherwise 判断，位于 {_path(doc_id, path)}）",
                )
            )
        slots = [
            _slot("action", _str_or_none(body.get("action"))),
            _Slot("branches", branch_ids, metas),
        ]
        return node, slots
    issues.append(
        _issue(
            doc_id,
            "structure",
            "unknown_node",
            f"节点 '{nid}' 类型 '{ntype}' 未知",
        )
    )
    return _empty_ir("Sequence", loc), []


def _slot(field: str, child_id: str | None) -> _Slot:
    return _Slot(field, [child_id] if child_id else [], [])


#: returns 接收名：``NewParam.<ASCII名>[:类型]``（强制 NewParam 前缀 + ASCII 标识符）。
_RETURN_KEY_TMPL = re.compile(
    r"NewParam\.([A-Za-z_][A-Za-z0-9_]*)(?::(str|int|float|bool|page_ref|object))?"
)


def _strip_return_name(key: object) -> tuple[str, str | None, str | None]:
    """returns 键 → (裸接收名, 内联类型, 错误消息或 None)。

    强制 ``NewParam.<ASCII名>[:类型]`` 形式：裸键（无 ``NewParam.`` 前缀）或非 ASCII
    变量名 → 返回错误消息（由调用方追加 ``syntax.invalid_return_name`` 校验问题）。
    """
    k = str(key).strip()
    m = _RETURN_KEY_TMPL.fullmatch(k)
    if m is None:
        return _legacy_return_fallback(k)
    return m.group(1), m.group(2), None


def _legacy_return_fallback(k: str) -> tuple[str, str | None, str | None]:
    """非规范 returns 键：尽力解析出裸名供下游（避免级联报错），并返回校验错误。"""
    name, inline = k, None
    if ":" in name:
        name, inline = name.split(":", 1)
        name = name.strip()
        inline = inline.strip() or None
    error = (
        f"returns 接收名 {k!r} 必须是 NewParam.<ASCII名>[:类型] 形式"
        "（变量名仅支持 ASCII 标识符，不支持中文/裸键）"
    )
    return name, inline, error


def _append_returns(
    doc_id: str, nid: str, returns: dict, issues: list
) -> list[tuple[str, str]]:
    """解析 returns 映射；非规范键追加 ``syntax.invalid_return_name`` 校验问题。"""
    pairs: list[tuple[str, str]] = []
    for k, v in returns.items():
        name, inline, error = _strip_return_name(k)
        if error is not None:
            issues.append(
                _issue(
                    doc_id,
                    "syntax",
                    "invalid_return_name",
                    f"{error}（位于 {_path(doc_id, f'nodes/{nid}')}）",
                )
            )
        pairs.append((name, str(v).strip() or inline or ""))
    return pairs


def _ref_ir(
    doc_id: str,
    nid: str,
    body: dict,
    loc: Loc,
    issues: list,
) -> IRNode:
    """构建 ref IRNode：target=文档名单段；args=实参表达式列表；returns=字典。"""
    target = body.get("target")
    if not isinstance(target, str) or not target.strip():
        issues.append(_issue(doc_id, "ref", "bad_syntax", f"ref 节点 '{nid}' 缺少 target 文档名"))
        return _empty_ir("ref", loc)
    args = body.get("args", [])
    args_tuple: tuple[str, ...] = ()
    if isinstance(args, list):
        args_tuple = tuple(str(item) for item in args)
    returns = body.get("returns", {})
    returns_pairs: list[tuple[str, str]] = []
    if isinstance(returns, dict):
        returns_pairs = _append_returns(doc_id, nid, returns, issues)
    return IRNode(
        kind="ref",
        ref_target=str(target).strip(),
        args=args_tuple,
        returns=tuple(returns_pairs),
        loc=loc,
    )


def _function_call_ir(
    doc_id: str,
    nid: str,
    body: dict,
    loc: Loc,
    issues: list,
) -> IRNode:
    """构建 FunctionCall IRNode：function + args + returns。"""
    path = f"nodes/{nid}"
    function = body.get("function")
    if not isinstance(function, str) or not function.strip():
        issues.append(
            _issue(
                doc_id,
                "structure",
                "missing_field",
                f"FunctionCall 缺少必需字段 'function'（位于 {_path(doc_id, path)}）",
            )
        )
    args = body.get("args", [])
    args_tuple: tuple[str, ...] = ()
    if isinstance(args, list):
        args_tuple = tuple(str(item) for item in args)
    else:
        issues.append(
            _issue(
                doc_id,
                "structure",
                "invalid_value",
                f"FunctionCall 的 args 必须是列表（位于 {_path(doc_id, path)}）",
            )
        )
    returns = body.get("returns", {})
    returns_pairs: list[tuple[str, str]] = []
    if isinstance(returns, dict):
        returns_pairs = _append_returns(doc_id, nid, returns, issues)
    else:
        issues.append(
            _issue(
                doc_id,
                "structure",
                "invalid_value",
                f"FunctionCall 的 returns 必须是映射（位于 {_path(doc_id, path)}）",
            )
        )
    return IRNode(
        kind="FunctionCall",
        function=(function or "").strip() if isinstance(function, str) else "",
        args=args_tuple,
        returns=tuple(returns_pairs),
        loc=loc,
    )


def _iter_subtrees(node: IRNode | None) -> list[IRNode]:
    """收集节点的直接子树（children + action + body + branches 目标）。

    条件字段（condition/until）不含子树；ref 无子。
    """
    if node is None:
        return []
    subs: list[IRNode] = []
    if node.children:
        subs.extend(node.children)
    if node.action is not None:
        subs.append(node.action)
    if node.body is not None:
        subs.append(node.body)
    for b in node.branches:
        if b.target is not None:
            subs.append(b.target)
    return subs


def _collect_ref_targets(node: IRNode | None) -> list[str]:
    """收集树中全部 ref 目标文档名。"""
    if node is None:
        return []
    targets: list[str] = []
    if node.kind == "ref" and node.ref_target:
        targets.append(node.ref_target.strip())
    for c in _iter_subtrees(node):
        targets.extend(_collect_ref_targets(c))
    return targets


def _check_ref_params(doc_id, nodes, resolver, issues) -> None:
    """校验 ref 节点参数对齐（args/returns 数量/字面量/类型）与跨文档环。"""

    def collect_refs(node: IRNode) -> list[IRNode]:
        refs: list[IRNode] = []
        if node.kind == "ref":
            refs.append(node)
        for c in _iter_subtrees(node):
            refs.extend(collect_refs(c))
        return refs

    all_refs: list[IRNode] = []
    for _, (node, _) in nodes.items():
        all_refs.extend(collect_refs(node))

    for ref in all_refs:
        target = (ref.ref_target or "").strip()
        if not target:
            continue
        # 跨文档环：被引文档（直接/间接）引回本文档
        if _leads_back_to(target, doc_id, resolver, set()):
            issues.append(
                _issue(
                    doc_id,
                    "ref",
                    "cross_doc_cycle",
                    f"引用 '{target}' 形成跨文档循环（引回 '{doc_id}'）",
                )
            )
        # 参数对齐：加载被引文档 inputs/outputs
        try:
            src = resolver.resolve(target)
        except Exception:
            issues.append(
                _issue(doc_id, "ref", "missing_doc", f"引用目标文档 '{target}' 不存在")
            )
            continue
        try:
            ref_doc = parse_document(src, resolver)
        except Exception:
            continue
        if not ref_doc.checks_ok():
            continue
        in_types = ref_doc.decl_inputs
        out_names = ref_doc.decl_outputs
        # args 数量 = inputs 数量
        if ref.args and len(ref.args) != len(in_types):
            issues.append(
                _issue(
                    doc_id,
                    "ref",
                    "args_mismatch",
                    f"引用 '{target}' args 数量 {len(ref.args)} ≠ 入参数量 {len(in_types)}",
                )
            )
        # returns 数量 = outputs 数量；键不得与本树 inputs 重名
        if ref.returns and len(ref.returns) != len(out_names):
            issues.append(
                _issue(
                    doc_id,
                    "ref",
                    "returns_mismatch",
                    f"引用 '{target}' returns 数量 {len(ref.returns)} ≠ 出参数量 {len(out_names)}",
                )
            )
        for key, _typ in ref.returns:
            if key in in_types:
                issues.append(
                    _issue(
                        doc_id,
                        "ref",
                        "name_conflict",
                        f"接收参数 '{key}' 与本树入参重名",
                    )
                )


def _leads_back_to(target: str, doc_id: str, resolver, seen: set[str]) -> bool:
    """被引文档 target 是否（直接/间接）引用回 doc_id。"""
    if target == doc_id:
        return True
    if target in seen:
        return False
    seen = seen | {target}
    try:
        src = resolver.resolve(target)
    except Exception:
        return False
    try:
        ref_doc = parse_document(src, resolver)
    except Exception:
        return False
    # 不依赖 checks_ok（参数校验失败不阻断环检测）；直接收集 ref 目标
    for ref in _collect_ref_targets(ref_doc.main_tree):
        if _leads_back_to(ref, doc_id, resolver, seen):
            return True
    for tree in ref_doc.free_trees:
        for ref in _collect_ref_targets(tree):
            if _leads_back_to(ref, doc_id, resolver, seen):
                return True
    return False


def _with_children(node: IRNode, children: list[IRNode]) -> IRNode:
    """给容器节点挂子节点（Root/Sequence/IfThenElse 用 children 字段）。"""
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


def _set(node: IRNode, **kwargs) -> IRNode:
    """构造带指定字段变更的 IRNode（frozen dataclass 替换）。"""
    return IRNode(
        kind=node.kind,
        loc=node.loc,
        description=node.description,
        css_hint=node.css_hint,
        target=node.target,
        predicate=node.predicate,
        children=node.children,
        branches=kwargs.get("branches", node.branches),
        condition=node.condition,
        action=kwargs.get("action", node.action),
        until=node.until,
        body=kwargs.get("body", node.body),
        max=node.max,
        mode=node.mode,
        ref_target=node.ref_target,
        args=node.args,
        returns=node.returns,
    )


def _issue(doc_id: str, prefix: str, code: str, message: str):
    return make_issue(prefix, code, message, _loc(doc_id, "$"))
