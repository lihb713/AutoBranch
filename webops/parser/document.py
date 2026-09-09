"""行为树文档结构解析：中间表示（设计决策 D1 第一阶段，任务 2.x）。

输入规范化后的 dict，输出**保留复合节点与 ``ref:`` 标记**的中间表示
（``DocumentIR`` / ``IRNode``），同步完成：

- block 定义识别（§4.1：根块 = 文档名，附加命名块供 ``this/块名`` 复用）
- 块接口声明提取（输入 / 输出，§5.3.3）
- 配置参数覆盖识别（§5.7.5，``timeout``/``retry``/``browser``）
- 结构合法性 / 验证条件 / 循环上界 三类校验问题收集

复合节点展开与块引用解析在第二阶段（``expand.py``）。

**文档格式（本模块明确定义）**：

::

    # 写法 A/B：顶层为「block <块名>:」定义（可多个）
    block 主流程:            # 根块 = 名字匹配文档名的块，无匹配取第一个
      inputs: ...
      outputs: ...
      Sequence: ...
    block 登录:              # 附加命名块，供 ref: this/登录 复用
      ...

    # 写法 C（极简）：整个 dict 即根块行为树（根块名 = 文档名）
    Sequence:
      - Step: ...

块体 = 接口声明（输入/输出）+ 配置参数覆盖（timeout/retry/browser 标量）+
恰好一个行为树节点键。
"""

from __future__ import annotations

from dataclasses import dataclass

from webops.parser.models import (
    BlockDecl,
    CheckIssue,
    ConfigOverride,
    DocumentSource,
    Loc,
    make_issue,
)
from webops.schema.types import TYPE_REGISTRY

#: 文档级块定义前缀：``block <块名>:``
BLOCK_PREFIX = "block "
#: 块接口声明键
DECL_KEYS = frozenset({"inputs", "outputs"})
#: 工具定义配置参数名（§4.2/§5.7.5，名称语义固定）
CONFIG_PARAMS = frozenset({"timeout", "retry", "browser"})
#: 节点键（基础 + 复合 + ref）
NODE_KEYS = frozenset(
    {
        "Action",
        "Condition",
        "Sequence",
        "Selector",
        "Repeat",
        "Finish",
        "Step",
        "Branch",
        "LoopUntil",
        "Retry",
        "IfThenElse",
        "ref",
    }
)
#: 复合节点键（§4.3，展开为基础节点组合）
COMPOSITE_KEYS = frozenset({"Step", "Branch", "LoopUntil", "Retry", "IfThenElse"})


@dataclass(frozen=True)
class IRBranch:
    """中间表示分支：条件（None = otherwise）→ 目标节点。"""

    when: IRNode | None = None
    target: IRNode | None = None


@dataclass(frozen=True)
class IRNode:
    """行为树中间表示节点（保留复合节点与 ref 标记）。

    :param kind: 节点键（``NODE_KEYS`` 之一）。
    :param loc: 文档位置。
    :param raw: 原始输入（调试/校验用）。
    其余字段按 kind 填充（见各解析函数）。
    """

    kind: str
    loc: Loc | None = None
    description: str | None = None
    css_hint: str | None = None
    target: str | None = None
    predicate: str | None = None
    children: tuple[IRNode, ...] = ()
    branches: tuple[IRBranch, ...] = ()
    condition: IRNode | None = None
    action: IRNode | None = None
    until: IRNode | None = None
    body: IRNode | None = None
    max: int | None = None
    mode: str | None = None
    ref_target: str | None = None
    bindings: tuple[tuple[str, str], ...] = ()
    args: tuple[tuple[str, str], ...] = ()
    returns: tuple[tuple[str, str], ...] = ()
    raw: object = None


@dataclass(frozen=True)
class DocumentIR:
    """单份文档的结构化中间表示。"""

    doc_id: str
    root_block: str
    blocks: dict[str, BlockDecl]
    root: IRNode
    ir_by_block: dict[str, IRNode]


@dataclass(frozen=True)
class StructureResult:
    """结构解析结果（中间表示 + 结构类校验问题）。"""

    ir: DocumentIR
    issues: tuple[CheckIssue, ...]


def _loc(doc_id: str, path: str) -> Loc:
    return Loc(doc_id=doc_id, path=path)


def _empty_ir(kind: str, loc: Loc | None = None) -> IRNode:
    return IRNode(kind=kind, loc=loc)


def parse_structure(doc: DocumentSource, raw: dict) -> StructureResult:
    """识别块定义与根流程，产出中间表示并收集结构类校验问题。"""
    issues: list[CheckIssue] = []
    blocks_raw: dict[str, dict | list] = {}
    extra_keys: list[str] = []
    for key, value in raw.items():
        if key.startswith(BLOCK_PREFIX) and isinstance(value, (dict, list)):
            blocks_raw[key[len(BLOCK_PREFIX) :].strip()] = value
        else:
            extra_keys.append(key)
    if blocks_raw and extra_keys:
        issues.append(
            make_issue(
                "structure",
                "invalid_flow",
                f"顶层混用 block 定义与其他键: {extra_keys}（位于 {doc.id}/$）",
                _loc(doc.id, "$"),
            )
        )
    if blocks_raw:
        # 方案 2：主块名必须等于文档名（行为树名）；无匹配 → 校验错误
        if doc.id not in blocks_raw:
            issues.append(
                make_issue(
                    "structure",
                    "missing_main_block",
                    f"行为树文档必须含名为 '{doc.id}' 的主块"
                    f"（主块名 = 行为树名；当前块: {sorted(blocks_raw)}，"
                    f"位于 {_path(doc.id, '$')}）",
                    _loc(doc.id, "$"),
                )
            )
            root_block = next(iter(blocks_raw))
        else:
            root_block = doc.id
        decls: dict[str, BlockDecl] = {}
        irs: dict[str, IRNode] = {}
        for name, body in blocks_raw.items():
            decl, tree_ir, sub = _parse_block_body(doc.id, name, body)
            decls[name] = decl
            irs[name] = tree_ir
            issues.extend(sub)
        root_ir = irs[root_block]
    else:
        root_block = doc.id
        decl, root_ir, sub = _parse_block_body(doc.id, doc.id, raw)
        decls = {doc.id: decl}
        irs = {doc.id: root_ir}
        issues.extend(sub)
    ir = DocumentIR(
        doc_id=doc.id,
        root_block=root_block,
        blocks=decls,
        root=root_ir,
        ir_by_block=irs,
    )
    return StructureResult(ir=ir, issues=tuple(issues))


def _parse_block_body(
    doc_id: str, name: str, body: dict | list
) -> tuple[BlockDecl, IRNode, list[CheckIssue]]:
    issues: list[CheckIssue] = []
    loc = _loc(doc_id, name)
    if isinstance(body, list):
        tree_ir = _parse_sequence(doc_id, name, body, issues)
        return (
            BlockDecl(name=name, doc_id=doc_id, loc=loc),
            tree_ir,
            issues,
        )
    inputs = _parse_decl_list(body.get("inputs"), doc_id, name, "inputs", issues)
    outputs = tuple(
        n
        for n, _ in _parse_decl_list(body.get("outputs"), doc_id, name, "outputs", issues)
    )
    overrides: list[ConfigOverride] = []
    for param in sorted(CONFIG_PARAMS):
        if param not in body:
            continue
        value = body[param]
        if isinstance(value, (int, float, str, bool)) and not isinstance(value, list):
            overrides.append(ConfigOverride(name=param, value=value, loc=loc))
        else:
            issues.append(
                make_issue(
                    "structure",
                    "invalid_config",
                    f"块 '{name}' 的配置参数 '{param}' 覆盖值必须是标量"
                    f"（位于 {_path(doc_id, name)}）",
                    loc,
                )
            )
    node_keys = [k for k in body if k not in DECL_KEYS and k not in CONFIG_PARAMS]
    if len(node_keys) != 1:
        issues.append(
            make_issue(
                "structure",
                "invalid_flow",
                f"块 '{name}' 必须且只能含一个行为树节点键"
                f"（当前: {node_keys or '无'}，位于 {_path(doc_id, name)}）",
                loc,
            )
        )
        return (
            BlockDecl(
                name=name,
                doc_id=doc_id,
                inputs=inputs,
                outputs=outputs,
                config_overrides=tuple(overrides),
                loc=loc,
            ),
            _empty_ir("Sequence", loc),
            issues,
        )
    tree_key = node_keys[0]
    tree_ir = _parse_node(doc_id, name, tree_key, body[tree_key], issues)
    return (
        BlockDecl(
            name=name,
            doc_id=doc_id,
            inputs=inputs,
            outputs=outputs,
            config_overrides=tuple(overrides),
            loc=loc,
        ),
        tree_ir,
        issues,
    )


def _parse_decl_list(
    value: object, doc_id: str, name: str, decl_name: str, issues: list[CheckIssue]
) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if decl_name == "inputs" and isinstance(value, dict):
        result: list[tuple[str, str]] = []
        for k, v in value.items():
            if not isinstance(k, str) or not isinstance(v, str):
                issues.append(
                    make_issue(
                        "structure",
                        "invalid_decl",
                        f"块 '{name}' 的 inputs 必须是 变量名: 类型 的映射"
                        f"（位于 {_path(doc_id, name)}）",
                        _loc(doc_id, name),
                    )
                )
                continue
            var = k.strip().lstrip("$")
            typ = v.strip()
            if not var:
                continue
            if typ and typ not in TYPE_REGISTRY:
                issues.append(
                    make_issue(
                        "structure",
                        "invalid_decl",
                        f"块 '{name}' 的输入 '{var}' 类型 '{typ}' 未登记"
                        f"（支持: {sorted(TYPE_REGISTRY)}，位于 {_path(doc_id, name)}）",
                        _loc(doc_id, name),
                    )
                )
                continue
            result.append((var, typ))
        return tuple(result)
    result: list[tuple[str, str]] = []
    if isinstance(value, str):
        items = [s.strip().lstrip("$") for s in value.split(",")]
    elif isinstance(value, list):
        items = [str(i).strip().lstrip("$") for i in value]
    else:
        issues.append(
            make_issue(
                "structure",
                "invalid_decl",
                f"块 '{name}' 的 {decl_name} 声明必须是字符串/列表"
                f"（或 inputs 用映射，位于 {_path(doc_id, name)}）",
                _loc(doc_id, name),
            )
        )
        return ()
    for s in items:
        if s:
            result.append((s, ""))
    return tuple(result)


def _path(doc_id: str, path: str) -> str:
    return f"{doc_id}/{path}"


def _parse_node(
    doc_id: str, path: str, key: str, value: object, issues: list[CheckIssue]
) -> IRNode:
    """按节点键解析单个节点（不含 ref 的键附加值处理，见 _parse_node_entry）。"""
    loc = _loc(doc_id, f"{path}/{key}")
    if key == "ref":
        return _parse_ref(doc_id, path, value, issues)
    if key == "Action":
        return _parse_action(doc_id, path, value, issues)
    if key == "Condition":
        return _parse_condition(doc_id, path, value, issues)
    if key == "Sequence":
        return _parse_sequence(doc_id, path, value, issues)
    if key == "Selector":
        return _parse_selector(doc_id, path, value, issues)
    if key == "Repeat":
        return _parse_repeat(doc_id, path, value, issues)
    if key == "Finish":
        desc = value if isinstance(value, str) else None
        return IRNode(kind="Finish", description=desc, loc=loc)
    if key in COMPOSITE_KEYS:
        return _parse_composite(doc_id, path, key, value, issues)
    issues.append(
        make_issue(
            "structure",
            "unknown_node",
            f"未知节点类型 '{key}'（位于 {_path(doc_id, f'{path}/{key}')}）",
            loc,
        )
    )
    return _empty_ir("Sequence", loc)


def _parse_node_entry(
    doc_id: str, path: str, entry: dict[str, object], issues: list[CheckIssue]
) -> IRNode:
    """解析节点项映射：恰好一个节点键；``ref`` 可附带 ``args``/``returns``。"""
    loc = _loc(doc_id, path)
    node_keys = [k for k in entry if k in NODE_KEYS]
    if len(node_keys) != 1:
        issues.append(
            make_issue(
                "structure",
                "invalid_node",
                f"节点项必须含且仅含一个节点键（实际: {list(entry)}，位于 {_path(doc_id, path)}）",
                loc,
            )
        )
        return _empty_ir("Sequence", loc)
    key = node_keys[0]
    extra = [k for k in entry if k not in NODE_KEYS]
    if key == "ref":
        bad = [k for k in extra if k not in ("args", "returns")]
        if bad:
            issues.append(
                make_issue(
                    "structure",
                    "invalid_node",
                    f"ref 节点不允许附带键: {bad}（位于 {_path(doc_id, path)}）",
                    loc,
                )
            )
        return _parse_ref(
            doc_id,
            path,
            entry[key],
            args=entry.get("args"),
            returns=entry.get("returns"),
            issues=issues,
        )
    if extra:
        issues.append(
            make_issue(
                "structure",
                "invalid_node",
                f"节点 '{key}' 不允许附带键: {extra}（位于 {_path(doc_id, path)}）",
                loc,
            )
        )
    return _parse_node(doc_id, path, key, entry[key], issues)


def _parse_ref(
    doc_id: str,
    path: str,
    target: object,
    args: object = None,
    returns: object = None,
    issues: list[CheckIssue] | None = None,
) -> IRNode:
    if issues is None:
        issues = []
    loc = _loc(doc_id, path)
    if not isinstance(target, str) or not target.strip():
        issues.append(
            make_issue(
                "ref",
                "bad_syntax",
                f"ref 目标必须是字符串（'this/块名' 或 '文档名/块名'，位于 {_path(doc_id, path)}）",
                loc,
            )
        )
        return _empty_ir("Sequence", loc)
    target = target.strip()
    parts = [p for p in target.split("/") if p]
    if len(parts) != 2:
        issues.append(
            make_issue(
                "ref",
                "bad_syntax",
                f"ref 目标 '{target}' 语法错误：应为 'this/块名' 或 '文档名/块名'"
                f"（位于 {_path(doc_id, path)}）",
                loc,
            )
        )
        return IRNode(kind="ref", ref_target=target, loc=loc)
    args_pairs = _parse_kv(args, "args", doc_id, path, issues)
    returns_pairs = _parse_kv(returns, "returns", doc_id, path, issues)
    return IRNode(
        kind="ref",
        ref_target=target,
        args=tuple(args_pairs),
        returns=tuple(returns_pairs),
        loc=loc,
    )


def _parse_kv(
    value: object, key_name: str, doc_id: str, path: str, issues: list[CheckIssue]
) -> list[tuple[str, str]]:
    """解析 ref 的 ``args``/``returns`` 映射：键值须为标量，返回 ``(k, str(v))``。"""
    pairs: list[tuple[str, str]] = []
    if value is None:
        return pairs
    if not isinstance(value, dict):
        issues.append(
            make_issue(
                "structure",
                "invalid_binding",
                f"ref 的 '{key_name}' 必须是映射（args/returns 键: 表达式，"
                f"位于 {_path(doc_id, path)}）",
                _loc(doc_id, path),
            )
        )
        return pairs
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, (str, int, float, bool)):
            issues.append(
                make_issue(
                    "structure",
                    "invalid_binding",
                    f"ref 的 '{key_name}' 项 '{k}' 的键或值不是标量（位于 {_path(doc_id, path)}）",
                    _loc(doc_id, path),
                )
            )
            continue
        pairs.append((k.strip(), str(v)))
    return pairs


def _parse_action(doc_id: str, path: str, value: object, issues: list[CheckIssue]) -> IRNode:
    loc = _loc(doc_id, f"{path}/Action")
    if isinstance(value, str):
        return IRNode(kind="Action", description=value, loc=loc)
    if isinstance(value, dict):
        desc = value.get("描述") or value.get("desc")
        css = value.get("CSS") or value.get("css")
        if not isinstance(desc, str) or not desc.strip():
            issues.append(
                make_issue(
                    "locatable",
                    "no_description",
                    f"Action 缺少自然语言描述（位于 {_path(doc_id, path)}）",
                    loc,
                )
            )
        if css is not None and not isinstance(css, str):
            issues.append(
                make_issue(
                    "structure",
                    "invalid_value",
                    f"Action 的 CSS 提示必须是字符串（位于 {_path(doc_id, path)}）",
                    loc,
                )
            )
            css = None
        return IRNode(
            kind="Action",
            description=desc if isinstance(desc, str) else "",
            css_hint=css if isinstance(css, str) else None,
            loc=loc,
        )
    issues.append(
        make_issue(
            "structure",
            "invalid_value",
            f"Action 的值必须是字符串或映射（描述/CSS，位于 {_path(doc_id, path)}）",
            loc,
        )
    )
    return IRNode(kind="Action", description="", loc=loc)


def _parse_condition(doc_id: str, path: str, value: object, issues: list[CheckIssue]) -> IRNode:
    loc = _loc(doc_id, f"{path}/Condition")
    if isinstance(value, str):
        return IRNode(kind="Condition", description=value, loc=loc)
    if isinstance(value, dict):
        desc = value.get("描述") or value.get("条件")
        target = value.get("目标") or value.get("对象")
        predicate = value.get("谓词") or value.get("比较")
        return IRNode(
            kind="Condition",
            description=desc if isinstance(desc, str) else "",
            target=target if isinstance(target, str) else None,
            predicate=predicate if isinstance(predicate, str) else None,
            loc=loc,
        )
    issues.append(
        make_issue(
            "structure",
            "invalid_value",
            f"Condition 的值必须是字符串或映射（位于 {_path(doc_id, path)}）",
            loc,
        )
    )
    return IRNode(kind="Condition", description="", loc=loc)


def _parse_sequence(doc_id: str, path: str, value: object, issues: list[CheckIssue]) -> IRNode:
    loc = _loc(doc_id, path)
    if isinstance(value, list):
        children: list[IRNode] = []
        for i, item in enumerate(value):
            child_loc = _loc(doc_id, f"{path}/{i}")
            if isinstance(item, dict):
                children.append(_parse_node_entry(doc_id, f"{path}/{i}", item, issues))
            else:
                issues.append(
                    make_issue(
                        "structure",
                        "invalid_node",
                        f"Sequence 第 {i} 项必须是节点映射（位于 {_path(doc_id, f'{path}/{i}')}）",
                        child_loc,
                    )
                )
                children.append(_empty_ir("Sequence", child_loc))
        return IRNode(kind="Sequence", children=tuple(children), loc=loc)
    if isinstance(value, dict):
        return IRNode(
            kind="Sequence",
            children=(_parse_node_entry(doc_id, path, value, issues),),
            loc=loc,
        )
    issues.append(
        make_issue(
            "structure",
            "invalid_value",
            f"Sequence 的值必须是节点列表或单个节点映射（位于 {_path(doc_id, path)}）",
            loc,
        )
    )
    return IRNode(kind="Sequence", loc=loc)


def _parse_selector(doc_id: str, path: str, value: object, issues: list[CheckIssue]) -> IRNode:
    loc = _loc(doc_id, path)
    branches: list[IRBranch] = []
    if not isinstance(value, list):
        issues.append(
            make_issue(
                "structure",
                "invalid_value",
                f"Selector 的值必须是分支列表（位于 {_path(doc_id, path)}）",
                loc,
            )
        )
        return IRNode(kind="Selector", loc=loc)
    for i, item in enumerate(value):
        branch_loc = _loc(doc_id, f"{path}/{i}")
        if not isinstance(item, dict):
            issues.append(
                make_issue(
                    "structure",
                    "invalid_node",
                    f"Selector 第 {i} 项必须是分支映射（when/then 或 otherwise，"
                    f"位于 {_path(doc_id, f'{path}/{i}')}）",
                    branch_loc,
                )
            )
            continue
        if "when" in item or "then" in item:
            when = _parse_condition(doc_id, f"{path}/{i}/when", item.get("when"), issues)
            target = _parse_target(doc_id, f"{path}/{i}/then", item.get("then"), issues)
            branches.append(IRBranch(when=when, target=target))
        elif "otherwise" in item:
            target = _parse_target(doc_id, f"{path}/{i}/otherwise", item.get("otherwise"), issues)
            branches.append(IRBranch(when=None, target=target))
        else:
            issues.append(
                make_issue(
                    "structure",
                    "invalid_node",
                    f"Selector 第 {i} 项缺少 when/then 或 otherwise（"
                    f"位于 {_path(doc_id, f'{path}/{i}')}）",
                    branch_loc,
                )
            )
    return IRNode(kind="Selector", branches=tuple(branches), loc=loc)


def _parse_target(doc_id: str, path: str, value: object, issues: list[CheckIssue]) -> IRNode:
    """分支目标解析：节点映射；裸字符串 = 引用同名命名块（§4.3 分支目标）。"""
    loc = _loc(doc_id, path)
    if isinstance(value, dict):
        return _parse_node_entry(doc_id, path, value, issues)
    if isinstance(value, str) and value.strip():
        return IRNode(kind="ref", ref_target=f"this/{value.strip()}", loc=loc)
    issues.append(
        make_issue(
            "structure",
            "invalid_target",
            f"分支目标必须是节点映射或块名（位于 {_path(doc_id, path)}）",
            loc,
        )
    )
    return _empty_ir("Sequence", loc)


def _parse_repeat(doc_id: str, path: str, value: object, issues: list[CheckIssue]) -> IRNode:
    loc = _loc(doc_id, path)
    if not isinstance(value, dict):
        issues.append(
            make_issue(
                "structure",
                "invalid_value",
                f"Repeat 的值必须是映射（位于 {_path(doc_id, path)}）",
                loc,
            )
        )
        return IRNode(kind="Repeat", loc=loc)
    mode = value.get("mode")
    if mode not in ("loop_until", "retry"):
        issues.append(
            make_issue(
                "structure",
                "invalid_value",
                f"Repeat 的 mode 必须是 loop_until 或 retry（位于 {_path(doc_id, path)}）",
                loc,
            )
        )
        mode = "retry"
    until = (
        _parse_condition(doc_id, f"{path}/until", value.get("until"), issues)
        if "until" in value
        else None
    )
    body = (
        _parse_target(doc_id, f"{path}/body", value.get("body"), issues)
        if "body" in value
        else _empty_ir("Sequence", _loc(doc_id, f"{path}/body"))
    )
    mx = _parse_max(doc_id, path, value.get("max"), issues)
    return IRNode(kind="Repeat", mode=mode, until=until, body=body, max=mx, loc=loc)


def _parse_composite(
    doc_id: str, path: str, key: str, value: object, issues: list[CheckIssue]
) -> IRNode:
    """复合节点解析（§4.3）：Step/Branch/LoopUntil/Retry/IfThenElse。"""
    loc = _loc(doc_id, f"{path}/{key}")
    if not isinstance(value, dict):
        issues.append(
            make_issue(
                "structure",
                "invalid_value",
                f"{key} 的值必须是映射（位于 {_path(doc_id, f'{path}/{key}')}）",
                loc,
            )
        )
        return IRNode(kind=key, loc=loc)
    if key == "Step":
        action = (
            _parse_action(doc_id, f"{path}/{key}/action", value.get("action"), issues)
            if "action" in value
            else None
        )
        expect = (
            _parse_condition(doc_id, f"{path}/{key}/expect", value.get("expect"), issues)
            if "expect" in value
            else None
        )
        if "action" not in value:
            issues.append(
                make_issue(
                    "structure",
                    "missing_field",
                    f"Step 缺少必需字段 'action'（位于 {_path(doc_id, path)}）",
                    loc,
                )
            )
        if "expect" not in value:
            issues.append(
                make_issue(
                    "verify",
                    "missing_condition",
                    f"Step 缺少验证条件 'expect'（每步必须有验证条件，位于 {_path(doc_id, path)}）",
                    loc,
                )
            )
        return IRNode(
            kind="Step",
            action=action or _empty_ir("Action", loc),
            condition=expect or _empty_ir("Condition", loc),
            loc=loc,
        )
    if key == "Branch":
        action = (
            _parse_action(doc_id, f"{path}/{key}/action", value.get("action"), issues)
            if "action" in value
            else None
        )
        branches = _parse_branches(doc_id, f"{path}/{key}/branches", value.get("branches"), issues)
        if "action" not in value:
            issues.append(
                make_issue(
                    "structure",
                    "missing_field",
                    f"Branch 缺少必需字段 'action'（位于 {_path(doc_id, path)}）",
                    loc,
                )
            )
        if not value.get("branches"):
            issues.append(
                make_issue(
                    "verify",
                    "missing_condition",
                    f"Branch 缺少分支条件 'branches'（必须有 when/otherwise 判断，"
                    f"位于 {_path(doc_id, path)}）",
                    loc,
                )
            )
        return IRNode(
            kind="Branch",
            action=action or _empty_ir("Action", loc),
            branches=branches,
            loc=loc,
        )
    if key == "LoopUntil":
        action = (
            _parse_action(doc_id, f"{path}/{key}/action", value.get("action"), issues)
            if "action" in value
            else None
        )
        until = (
            _parse_condition(doc_id, f"{path}/{key}/until", value.get("until"), issues)
            if "until" in value
            else None
        )
        mx = _parse_max(doc_id, path, value.get("max"), issues)
        if "action" not in value:
            issues.append(
                make_issue(
                    "structure",
                    "missing_field",
                    f"LoopUntil 缺少必需字段 'action'（位于 {_path(doc_id, path)}）",
                    loc,
                )
            )
        if "until" not in value:
            issues.append(
                make_issue(
                    "verify",
                    "missing_condition",
                    f"LoopUntil 缺少终止条件 'until'（位于 {_path(doc_id, path)}）",
                    loc,
                )
            )
        return IRNode(
            kind="LoopUntil",
            action=action or _empty_ir("Action", loc),
            until=until or _empty_ir("Condition", loc),
            max=mx,
            loc=loc,
        )
    if key == "Retry":
        body = (
            _parse_target(doc_id, f"{path}/{key}/body", value.get("body"), issues)
            if "body" in value
            else None
        )
        mx = _parse_max(doc_id, path, value.get("max"), issues)
        if "body" not in value:
            issues.append(
                make_issue(
                    "structure",
                    "missing_field",
                    f"Retry 缺少必需字段 'body'（位于 {_path(doc_id, path)}）",
                    loc,
                )
            )
        return IRNode(kind="Retry", body=body or _empty_ir("Sequence", loc), max=mx, loc=loc)
    if key == "IfThenElse":
        cond = (
            _parse_condition(doc_id, f"{path}/{key}/if", value.get("if"), issues)
            if "if" in value
            else None
        )
        then = (
            _parse_target(doc_id, f"{path}/{key}/then", value.get("then"), issues)
            if "then" in value
            else None
        )
        els = (
            _parse_target(doc_id, f"{path}/{key}/else", value.get("else"), issues)
            if "else" in value
            else None
        )
        missing = [f for f in ("if", "then", "else") if f not in value]
        if missing:
            issues.append(
                make_issue(
                    "structure",
                    "missing_field",
                    f"IfThenElse 缺少必需字段: {missing}（位于 {_path(doc_id, path)}）",
                    loc,
                )
            )
        return IRNode(
            kind="IfThenElse",
            condition=cond or _empty_ir("Condition", loc),
            children=(
                then or _empty_ir("Sequence", loc),
                els or _empty_ir("Sequence", loc),
            ),
            loc=loc,
        )
    return _empty_ir("Sequence", loc)


def _parse_branches(
    doc_id: str, path: str, value: object, issues: list[CheckIssue]
) -> tuple[IRBranch, ...]:
    branches: list[IRBranch] = []
    if not isinstance(value, list):
        if value is not None:
            issues.append(
                make_issue(
                    "structure",
                    "invalid_value",
                    f"Branch 的 branches 必须是列表（位于 {_path(doc_id, path)}）",
                    _loc(doc_id, path),
                )
            )
        return ()
    for i, item in enumerate(value):
        branch_loc = _loc(doc_id, f"{path}/{i}")
        if not isinstance(item, dict):
            issues.append(
                make_issue(
                    "structure",
                    "invalid_node",
                    f"Branch 第 {i} 项必须是分支映射（位于 {_path(doc_id, f'{path}/{i}')}）",
                    branch_loc,
                )
            )
            continue
        if "when" in item or "then" in item:
            when = _parse_condition(doc_id, f"{path}/{i}/when", item.get("when"), issues)
            target = _parse_target(doc_id, f"{path}/{i}/then", item.get("then"), issues)
            branches.append(IRBranch(when=when, target=target))
        elif "otherwise" in item:
            target = _parse_target(doc_id, f"{path}/{i}/otherwise", item.get("otherwise"), issues)
            branches.append(IRBranch(when=None, target=target))
        else:
            issues.append(
                make_issue(
                    "structure",
                    "invalid_node",
                    f"Branch 第 {i} 项缺少 when/then 或 otherwise（"
                    f"位于 {_path(doc_id, f'{path}/{i}')}）",
                    branch_loc,
                )
            )
    return tuple(branches)


def _parse_max(doc_id: str, path: str, value: object, issues: list[CheckIssue]) -> int | None:
    """循环上界解析（缺失/非法 → 校验问题，§4.4 循环有上界）。"""
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
