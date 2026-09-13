"""复合节点展开与块引用解析（设计决策 D1 第二阶段，任务 3.x/4.x/5.x 展开期）。

在中间表示之上执行：

- 复合节点展开（§4.3 精确语义，规则集中于 ``EXPANSION_RULES`` 单一映射表）
- 引用解析（``ref: 文档名`` 跨文档整树）与循环引用检测、
  展开深度防护（静态，跨 ``blocks_tree`` 的 ref 图走查）
- 每块独立预展开为基础树：``blocks_tree[块名]``（ref 保留为 ``RefNode``，
  运行期动态调用，不再内联展开）
- 变量契约校验（§5.3.2 作用域：只读写自己的 schema，单段 ``this/<名>``）
- 函数式传参契约校验（ref ``args`` 注入声明输入、``returns`` 接收声明输出，
  ``inputs`` 全必填、``outputs`` 全赋值）
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from webops.parser.document import IRNode
from webops.parser.models import (
    ActionNode,
    BranchSpec,
    CheckIssue,
    ConditionNode,
    FinishNode,
    Loc,
    Node,
    RefNode,
    RepeatNode,
    SelectorNode,
    SequenceNode,
    make_issue,
)

#: ``[[get:path]]`` 读取引用（叶子执行前程序替换为真实值）；path 为裸变量名（兼容 this/名）
_GET_TMPL = re.compile(r"\[\[\s*get:\s*((?:this/)?[^\[\]]+?)\s*\]\]")
#: ``[[set[:type]:path]]`` 写入声明；type ∈ TYPE_REGISTRY token（可省略），path 裸名（兼容 this/名）
_SET_TMPL = re.compile(
    r"\[\[\s*set:(?:(str|int|float|bool|page_ref):)?\s*((?:this/)?[^\[\]:]+?)\s*\]\]"
)
#: 裸 ``this/path``（兼容旧写法；用于 scope 检查）
_PLAIN_PATH = re.compile(r"(?<![\w$])this/([^\s{}|>]+)")


def _bare_name(path: str) -> str:
    """归一化为裸变量名：``this/param`` / ``$this/param`` → ``param``。"""
    p = path.strip()
    for prefix in ("this/", "$this/"):
        if p.startswith(prefix):
            return p[len(prefix) :]
    if p in ("this", "$this"):
        return ""
    return p


def _iter_set_decls(text: str) -> list[tuple[str, str]]:
    """提取写入声明 ``(裸变量名, type)``（type ∈ TYPE_REGISTRY token/空串）。"""
    decls: list[tuple[str, str]] = []
    for m in _SET_TMPL.finditer(text):
        type_name = (m.group(1) or "").strip()
        path = _bare_name(m.group(2) or "")
        if path:
            decls.append((path, type_name))
    return decls


def _iter_get_paths(text: str) -> list[str]:
    """提取描述中的全部读取变量名（``[[get:...]]`` → 裸名）。"""
    names: list[str] = []
    for m in _GET_TMPL.finditer(text):
        name = _bare_name(m.group(1))
        if name:
            names.append(name)
    return names


def _iter_set_paths(text: str) -> list[str]:
    """提取描述中的全部写入变量名（``[[set:...]]`` → 裸名）。"""
    return [path for path, _ in _iter_set_decls(text)]


def _iter_schema_paths(text: str) -> list[str]:
    """从自然语言描述中提取全部变量路径（读引用/写声明/裸 this/ 兼容）。"""
    paths: list[str] = []
    rest = _GET_TMPL.sub("", text)
    rest = _SET_TMPL.sub("", rest)
    paths.extend(_iter_get_paths(text))
    paths.extend(_iter_set_paths(text))
    for m in _PLAIN_PATH.finditer(rest):
        p = m.group(1).strip()
        if p:
            paths.append(p)
    return paths


def _schema_segments(path: str) -> tuple[str, ...] | None:
    """归一化为裸变量名后按 ``/`` 分段（``this/username`` → ``('username',)``）。

    去 this/ 后仅单段合法；非法/空返回 None。
    """
    p = _bare_name(path)
    parts = [s for s in p.split("/") if s]
    return tuple(parts) if parts else None


def _display_path(path: str) -> str:
    """展示/存储用的裸变量名（去 this/ 前缀）。"""
    return _bare_name(path)


@dataclass
class ExpandContext:
    """展开期共享上下文：校验问题（一文档一树，ref 运行时按文档名加载）。"""

    max_depth: int
    issues: list[CheckIssue] = field(default_factory=list)

    def add_issue(self, prefix: str, code: str, message: str, loc: Loc | None = None) -> None:
        self.issues.append(make_issue(prefix, code, message, loc))


@dataclass(frozen=True)
class ExpansionResult:
    """展开结果：主树基础树 + 展开期校验问题。"""

    tree: Node
    issues: tuple[CheckIssue, ...]


def expand_document(
    main_ir: IRNode | None,
    ctx: ExpandContext,
    decl_inputs: dict[str, str] | None = None,
) -> ExpansionResult:
    """展开主树 IR 为基础树（复合节点展开；ref 保留为 RefNode）。

    :param decl_inputs: 文档级入参声明（get 已定义校验用）。
    """
    if main_ir is None:
        return ExpansionResult(tree=SequenceNode(), issues=tuple(ctx.issues))
    tree = _expand_ir(main_ir, ctx, 0)
    _check_get_defined(ctx, tree, set(decl_inputs or {}))
    return ExpansionResult(tree=tree, issues=tuple(ctx.issues))


def _check_get_defined(
    ctx: ExpandContext, tree: Node, input_names: set[str]
) -> None:
    """主树内 ``[[get:this/x]]`` 变量已定义校验（§5）。

    get 可读取 = 文档级 inputs 声明 + 主树内 ``[[set:...]]`` 目标
    + ref returns 目标变量；output 不构成 get 源。未定义 → get_undeclared。
    """
    defined = set(input_names) | _collect_output_assignment_names_ir(tree)

    def walk(node: Node) -> None:
        if isinstance(node, ActionNode):
            for name in _iter_get_paths(node.description or ""):
                if name not in defined:
                    ctx.add_issue(
                        "scope",
                        "get_undeclared",
                        f"读取变量 '{name}' 未定义"
                        f"（get 只能读 inputs 声明、块内 set 或 ref returns 目标）",
                        node.loc,
                    )
        elif isinstance(node, ConditionNode):
            for name in _iter_get_paths(node.description or ""):
                if name not in defined:
                    ctx.add_issue(
                        "scope",
                        "get_undeclared",
                        f"读取变量 '{name}' 未定义"
                        f"（get 只能读 inputs 声明、块内 set 或 ref returns 目标）",
                        node.loc,
                    )
        if isinstance(node, SequenceNode):
            for c in node.children:
                walk(c)
        elif isinstance(node, SelectorNode):
            for b in node.branches:
                if b.condition is not None:
                    walk(b.condition)
                walk(b.child)
        elif isinstance(node, RepeatNode):
            if node.until is not None:
                walk(node.until)
            walk(node.body)

    walk(tree)


def _collect_output_assignment_names_ir(node: Node) -> set[str]:
    """基础树内赋值点变量名集合（Action 的 set 目标 + RefNode 的 returns 接收名）。"""
    names: set[str] = set()
    if isinstance(node, RefNode):
        for recv, _typ in node.returns:
            if recv:
                names.add(recv)
        return names
    if isinstance(node, ActionNode):
        return _set_decl_names(node.description or "")
    if isinstance(node, SequenceNode):
        for c in node.children:
            names |= _collect_output_assignment_names_ir(c)
    elif isinstance(node, SelectorNode):
        for b in node.branches:
            if b.condition is not None:
                names |= _collect_output_assignment_names_ir(b.condition)
            names |= _collect_output_assignment_names_ir(b.child)
    elif isinstance(node, RepeatNode):
        if node.until is not None:
            names |= _collect_output_assignment_names_ir(node.until)
        names |= _collect_output_assignment_names_ir(node.body)
    return names


def _set_decl_names(desc: str) -> set[str]:
    """叶子描述中单段 ``[[set:...:this/<名>]]`` 的目标名集合。"""
    names: set[str] = set()
    for path, _ in _iter_set_decls(desc):
        segs = _schema_segments(path)
        if segs is not None and len(segs) == 1:
            names.add(segs[0])
    return names


def _collect_output_assignment_names(node: IRNode | None) -> set[str]:
    """块体树内（不含 ref 子块内部）的赋值点：叶子 set 目标或本块 ref 的 returns 目标。

    ref 子块内部如何产出其输出由该子块自己校验（递归性质，因每个块都被检查）。
    赋值点只认本帧内的 set 或本块 returns 的目标变量（单段）。
    """
    if node is None:
        return set()
    names: set[str] = set()
    if node.kind == "ref":
        for recv, _typ in node.returns:
            if recv:
                names.add(recv)
        return names
    if node.kind == "Action":
        return _set_decl_names(node.description or "")
    for child in node.children:
        names |= _collect_output_assignment_names(child)
    for b in node.branches:
        if b.when is not None:
            names |= _collect_output_assignment_names(b.when)
        if b.target is not None:
            names |= _collect_output_assignment_names(b.target)
    for sub in (node.action, node.condition, node.until, node.body):
        if sub is not None:
            names |= _collect_output_assignment_names(sub)
    return names


def _collect_get_refs(node: IRNode | None) -> list[tuple[str, Loc | None]]:
    """收集块内全部叶子（Action/Condition/Finish）描述中的 ``[[get:this/x]]`` 引用。

    返回 ``(变量名, loc)`` 列表，供 get 已定义校验使用。
    """
    if node is None:
        return []
    refs: list[tuple[str, Loc | None]] = []
    if node.kind in ("Action", "Condition"):
        desc = node.description or ""
        for name in _iter_get_paths(desc):
            refs.append((name, node.loc))
        return refs
    for child in node.children:
        refs.extend(_collect_get_refs(child))
    for b in node.branches:
        if b.when is not None:
            refs.extend(_collect_get_refs(b.when))
        if b.target is not None:
            refs.extend(_collect_get_refs(b.target))
    for sub in (node.action, node.condition, node.until, node.body):
        if sub is not None:
            refs.extend(_collect_get_refs(sub))
    return refs


def _check_schema_path(ctx: ExpandContext, path_str: str, loc: Loc | None) -> None:
    """变量契约校验：仅 ``this/<名>`` 单段合法（§5 函数式传参后无跨帧读写）。"""
    display = _display_path(path_str)
    at = loc.path if loc else "?"
    segs = _schema_segments(path_str)
    if segs is None:
        ctx.add_issue(
            "scope",
            "out_of_scope",
            f"变量引用 '{display}' 非法（应为 this/变量，位于 {at}）",
            loc,
        )
        return
    if len(segs) == 1:
        return
    ctx.add_issue(
        "scope",
        "out_of_scope",
        f"变量 '{display}' 指向多段路径（this/子块/变量），越出本块可见作用域"
        f"（函数式传参后只可读/写本帧 this/变量，位于 {at}）",
        loc,
    )


def _scope_check_texts(ctx: ExpandContext, loc: Loc | None, *texts: str | None) -> None:
    for text in texts:
        if not text:
            continue
        for p in _iter_schema_paths(text):
            _check_schema_path(ctx, p, loc)


def _expand_ir(node: IRNode, ctx: ExpandContext, depth: int) -> Node:
    if depth > ctx.max_depth:
        at = node.loc.path if node.loc else "?"
        ctx.add_issue(
            "expand",
            "depth_exceeded",
            f"展开嵌套过深（超过 {ctx.max_depth} 层上限，位于 {at}）",
            node.loc,
        )
        return SequenceNode(loc=node.loc)
    kind = node.kind
    rule = EXPANSION_RULES.get(kind)
    if rule is not None:
        return rule(node, ctx, depth)
    if kind == "Action":
        _scope_check_texts(ctx, node.loc, node.description)
        decls = _iter_set_decls(node.description or "")
        set_targets = tuple(_display_path(p) for p, _ in decls)
        set_decls = tuple((_display_path(p), t) for p, t in decls)
        return ActionNode(
            description=node.description or "",
            css_hint=node.css_hint,
            set_targets=set_targets,
            set_decls=set_decls,
            loc=node.loc,
        )
    if kind == "Condition":
        _scope_check_texts(ctx, node.loc, node.description, node.target, node.predicate)
        return ConditionNode(
            description=node.description or "",
            target=node.target,
            predicate=node.predicate,
            loc=node.loc,
        )
    if kind == "Root":
        # Root：真实节点类型（子限制 1），展开其唯一子节点
        children = tuple(_expand_ir(c, ctx, depth + 1) for c in node.children)
        return SequenceNode(children=children, loc=node.loc)
    if kind == "Sequence":
        return SequenceNode(
            children=tuple(_expand_ir(c, ctx, depth + 1) for c in node.children),
            loc=node.loc,
        )
    if kind == "Selector":
        branches = tuple(
            BranchSpec(
                condition=(
                    _as_condition(_expand_ir(b.when, ctx, depth + 1))
                    if b.when is not None
                    else None
                ),
                child=_expand_ir(b.target, ctx, depth + 1),
            )
            for b in node.branches
        )
        return SelectorNode(branches=branches, loc=node.loc)
    if kind == "Repeat":
        body = _expand_ir(
            node.body or _empty_ir("Sequence", node.loc), ctx, depth + 1
        )
        until = (
            _as_condition(_expand_ir(node.until, ctx, depth + 1))
            if node.until is not None
            else None
        )
        return RepeatNode(
            body=body,
            mode=node.mode or "retry",
            until=until,
            max=node.max or 0,
            loc=node.loc,
        )
    if kind == "Finish":
        return FinishNode(loc=node.loc)
    if kind == "ref":
        return _expand_ref(node, ctx)
    return SequenceNode(loc=node.loc)


def _as_condition(node: Node) -> ConditionNode:
    """防御：将任意展开结果归一为 ConditionNode。"""
    if isinstance(node, ConditionNode):
        return node
    if isinstance(node, ActionNode):
        return ConditionNode(description=node.description, loc=node.loc)
    return ConditionNode(loc=node.loc)


def _empty_ir(kind: str, loc: Loc | None = None) -> IRNode:
    return IRNode(kind=kind, loc=loc)


def _rule_step(
    node: IRNode, ctx: ExpandContext, depth: int
) -> Node:
    """Step = Sequence(Action + Condition)。"""
    action = _expand_ir(
        node.action or _empty_ir("Action", node.loc), ctx, depth + 1
    )
    cond = _expand_ir(
        node.condition or _empty_ir("Condition", node.loc), ctx, depth + 1
    )
    return SequenceNode(children=(action, _as_condition(cond)), loc=node.loc)


def _rule_branch(
    node: IRNode, ctx: ExpandContext, depth: int
) -> Node:
    """Branch = Action + Selector（顺序检查 when，第一个命中生效，无匹配走 otherwise）。"""
    action = _expand_ir(
        node.action or _empty_ir("Action", node.loc), ctx, depth + 1
    )
    branches = tuple(
        BranchSpec(
            condition=(
                _as_condition(_expand_ir(b.when, ctx, depth + 1))
                if b.when is not None
                else None
            ),
            child=_expand_ir(b.target, ctx, depth + 1),
        )
        for b in node.branches
    )
    selector = SelectorNode(branches=branches, loc=node.loc)
    return SequenceNode(children=(action, selector), loc=node.loc)


def _rule_loop_until(
    node: IRNode, ctx: ExpandContext, depth: int
) -> Node:
    """LoopUntil = Repeat(mode=loop_until, until=条件, max=上限)：每轮先判 until。"""
    action = _expand_ir(
        node.action or _empty_ir("Action", node.loc), ctx, depth + 1
    )
    until = _as_condition(
        _expand_ir(
            node.until or _empty_ir("Condition", node.loc), ctx, depth + 1
        )
    )
    return RepeatNode(
        body=action, mode="loop_until", until=until, max=node.max or 0, loc=node.loc
    )


def _rule_retry(
    node: IRNode, ctx: ExpandContext, depth: int
) -> Node:
    """Retry = Repeat(mode=retry, max=上限)：每轮后判 body 执行结果。"""
    body = _expand_ir(
        node.body or _empty_ir("Sequence", node.loc), ctx, depth + 1
    )
    return RepeatNode(
        body=body, mode="retry", until=None, max=node.max or 0, loc=node.loc
    )


def _rule_if_then_else(
    node: IRNode, ctx: ExpandContext, depth: int
) -> Node:
    """IfThenElse = Selector(if→then, else→else)：先判 if 条件。"""
    cond = _as_condition(
        _expand_ir(
            node.condition or _empty_ir("Condition", node.loc), ctx, depth + 1
        )
    )
    then_node = node.children[0] if node.children else None
    else_node = node.children[1] if len(node.children) > 1 else None
    then = _expand_ir(
        then_node or _empty_ir("Sequence", node.loc), ctx, depth + 1
    )
    els = _expand_ir(
        else_node or _empty_ir("Sequence", node.loc), ctx, depth + 1
    )
    return SelectorNode(
        branches=(
            BranchSpec(condition=cond, child=then),
            BranchSpec(condition=None, child=els),
        ),
        loc=node.loc,
    )


#: 复合节点展开规则映射（§4.3 精确语义，单一映射表，供表驱动测试直接覆盖）
EXPANSION_RULES: dict[str, Callable[[IRNode, ExpandContext, int], Node]] = {
    "Step": _rule_step,
    "Branch": _rule_branch,
    "LoopUntil": _rule_loop_until,
    "Retry": _rule_retry,
    "IfThenElse": _rule_if_then_else,
}


def _expand_ref(node: IRNode, ctx: ExpandContext) -> Node:
    """ref 保留为 ``RefNode``（不内联）：一文档一树下目标为另一文档整棵树。

    参数对齐/目标存在/跨文档环等静态校验已在 onedoc 解析期完成（``_check_ref_params``）；
    此处仅把 IR ref 转为基础 ``RefNode``，运行时 ``_tick_ref`` 按文档名加载。
    """
    loc = node.loc
    at = loc.path if loc else "?"
    target = (node.ref_target or "").strip()
    if not target or "/" in target:
        ctx.add_issue(
            "ref",
            "bad_syntax",
            f"ref 目标 '{target}' 语法错误（应为文档名单段，位于 {at}）",
            loc,
        )
        return SequenceNode(loc=loc)
    return RefNode(ref_target=target, args=node.args, returns=node.returns, loc=loc)
