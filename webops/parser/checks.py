"""展开后校验与校验报告汇总（§4.4 校验类，任务 5.1 展开后合法性 / 5.4 / 5.5 / 5.6）。

设计决策 D4：校验按类别独立成规则，汇总为统一 ``CheckReport``。
展开期校验（引用、循环上界、变量契约、绑定）在 ``expand.py`` 中完成；
本模块负责**展开后**的合法性、可定位性、验证条件与谓词可校验性检查，
并汇总最终报告。
"""

from __future__ import annotations

from webops.parser.models import (
    ActionNode,
    CheckIssue,
    CheckReport,
    ConditionNode,
    FinishNode,
    Node,
    RefNode,
    RepeatNode,
    SelectorNode,
    SequenceNode,
    make_issue,
)

_BASIC_TYPES = (
    ActionNode,
    ConditionNode,
    SequenceNode,
    SelectorNode,
    RepeatNode,
    FinishNode,
    RefNode,
)


def post_expansion_checks(tree: Node) -> tuple[CheckIssue, ...]:
    """展开后合法性：遍历断言展开树仅含基础节点（§4.4 第 2 类）。"""
    issues: list[CheckIssue] = []
    _walk_expanded(tree, issues)
    return tuple(issues)


def _walk_expanded(node: Node, issues: list[CheckIssue]) -> None:
    if not isinstance(node, _BASIC_TYPES):
        loc = getattr(node, "loc", None)
        at = loc.path if loc else "?"
        issues.append(
            make_issue(
                "expand",
                "residual_composite",
                f"展开后的行为树仍含非法节点: {type(node).__name__}（位于 {at}）",
                loc,
            )
        )
        return
    if isinstance(node, SequenceNode):
        for c in node.children:
            _walk_expanded(c, issues)
    elif isinstance(node, SelectorNode):
        for b in node.branches:
            if b.condition is not None:
                _walk_expanded(b.condition, issues)
            _walk_expanded(b.child, issues)
    elif isinstance(node, RepeatNode):
        if node.until is not None:
            _walk_expanded(node.until, issues)
        _walk_expanded(node.body, issues)


def leaf_locatable_predicate_checks(tree: Node) -> tuple[CheckIssue, ...]:
    """可定位性 + 验证条件 + 谓词可校验（§4.4 第 6/7/8 类，作用于展开树叶子）。"""
    issues: list[CheckIssue] = []
    _walk_leaves(tree, issues)
    return tuple(issues)


def _walk_leaves(node: Node, issues: list[CheckIssue]) -> None:
    at = node.loc.path if node.loc else "?"
    if isinstance(node, ActionNode):
        if not node.css_hint and not (node.description or "").strip():
            issues.append(
                make_issue(
                    "locatable",
                    "not_locatable",
                    f"动作不可定位: 无 CSS 提示且无自然语言描述（位于 {at}）",
                    node.loc,
                )
            )
        return
    if isinstance(node, ConditionNode):
        if not (node.description or "").strip():
            issues.append(
                make_issue(
                    "predicate",
                    "empty_condition",
                    f"条件谓词不可校验: 缺少自然语言描述（位于 {at}）",
                    node.loc,
                )
            )
        return
    if isinstance(node, SequenceNode):
        for c in node.children:
            _walk_leaves(c, issues)
    elif isinstance(node, SelectorNode):
        for b in node.branches:
            if b.condition is not None:
                _walk_leaves(b.condition, issues)
            _walk_leaves(b.child, issues)
    elif isinstance(node, RepeatNode):
        if node.until is not None:
            _walk_leaves(node.until, issues)
        _walk_leaves(node.body, issues)


def build_report(issues: list[CheckIssue]) -> CheckReport:
    """汇总校验报告：去重 + 按位置/错误码排序（§4.4/§5.6 输出契约）。"""
    seen: set[tuple[str, str, str]] = set()
    unique: list[CheckIssue] = []
    for iss in issues:
        key = (iss.code, iss.message, iss.loc.path if iss.loc else "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(iss)
    unique.sort(key=lambda i: (i.loc.path if i.loc else "", i.code))
    return CheckReport(ok=not unique, issues=tuple(unique))
