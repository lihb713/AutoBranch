"""行为树文档结构解析：节点级中间表示（一文档一树，§12）。

输入为单个节点的 dict，输出**保留复合节点与 ``ref:`` 标记**的中间表示
（``IRNode``）。一文档一树文档（``tree``/``nodes``/``root``）的节点池
由 ``onedoc.py`` 解析，本模块提供各节点类型的单节点解析（Step/Sequence/
ref/...）。ref 目标为**文档名单段**（引用另一文档整棵树）。

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
    CheckIssue,
    Loc,
    make_issue,
)

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


def _loc(doc_id: str, path: str) -> Loc:
    return Loc(doc_id=doc_id, path=path)


def _empty_ir(kind: str, loc: Loc | None = None) -> IRNode:
    return IRNode(kind=kind, loc=loc)


def _path(doc_id: str, path: str) -> str:
    return f"{doc_id}/{path}"


def _parse_node(
    doc_id: str, path: str, key: str, value: object, issues: list[CheckIssue]
) -> IRNode:
    """按节点键解析单个节点（一文档一树；ref/Sequence 由 onedoc 处理）。"""
    loc = _loc(doc_id, f"{path}/{key}")
    if key == "ref":
        ref_target = str(value).strip() if isinstance(value, str) else ""
        return IRNode(kind="ref", ref_target=ref_target, loc=loc)
    if key == "Action":
        return _parse_action(doc_id, path, value, issues)
    if key == "Condition":
        return _parse_condition(doc_id, path, value, issues)
    if key == "Sequence":
        return _empty_ir("Sequence", loc)
    if key == "Selector":
        return _empty_ir("Selector", loc)
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



def _parse_target(
    doc_id: str, path: str, value: object, issues: list[CheckIssue]
) -> IRNode:
    """把分支/循环体的目标（节点映射或文档名单段字符串）解析为 IRNode。"""
    loc = _loc(doc_id, path)
    if isinstance(value, dict):
        node_keys = [k for k in value if k in NODE_KEYS or k in COMPOSITE_KEYS]
        if len(node_keys) == 1:
            return _parse_node(doc_id, path, node_keys[0], value[node_keys[0]], issues)
        issues.append(
            make_issue(
                "structure",
                "invalid_node",
                f"目标节点必须含一个节点键（位于 {_path(doc_id, path)}）",
                loc,
            )
        )
        return _empty_ir("Sequence", loc)
    if isinstance(value, str) and value.strip():
        return IRNode(kind="ref", ref_target=value.strip(), loc=loc)
    issues.append(
        make_issue(
            "structure",
            "invalid_value",
            f"目标必须是节点映射或文档名（位于 {_path(doc_id, path)}）",
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
