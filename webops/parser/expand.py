"""复合节点展开与块引用解析（设计决策 D1 第二阶段，任务 3.x/4.x/5.x 展开期）。

在中间表示之上执行：

- 复合节点展开（§4.3 精确语义，规则集中于 ``EXPANSION_RULES`` 单一映射表）
- 块引用解析（``this/块名``、``文档名/块名``、``文档名/文档名`` 跨文档整树）
  与循环引用检测、展开深度防护
- 引用处建立独立 schema 命名空间帧并记录参数绑定（§5.7.3/§5.7.4）
- 变量契约校验（§5.3.2 作用域：只读写自己的 schema 与直接子块）
- 绑定输入契约校验（引用处 ``写入`` 注入被引用块声明输入）
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from webops.parser import document as document_mod
from webops.parser.document import DocumentIR, IRNode
from webops.parser.errors import RefNotFoundError
from webops.parser.models import (
    ActionNode,
    BranchSpec,
    CheckIssue,
    ConditionNode,
    FinishNode,
    FrameInfo,
    Loc,
    Node,
    ParamBinding,
    RepeatNode,
    SelectorNode,
    SequenceNode,
    make_issue,
)
from webops.parser.refs import RefResolver
from webops.parser.yamlio import normalize_document

#: ``{{get:this/path}}`` 读取引用（叶子执行前程序替换为真实值）
_GET_TMPL = re.compile(r"\{\{\s*get:\s*this/([^{}]+?)\s*\}\}")
#: ``{{set[:type]:path}}`` 写入声明；type ∈ TYPE_REGISTRY token（可省略），path 可带 this/ 或不带
_SET_TMPL = re.compile(
    r"\{\{\s*set:(?:(str|int|float|bool|page_ref):)?\s*((?:this/)?[^{}:]+?)\s*\}\}"
)
#: 裸 ``this/path``（绑定/传参路径等）
_PLAIN_PATH = re.compile(r"(?<![\w$])this/([^\s{}|>]+)")


def _normalize_set_path(path: str) -> str:
    """路径补全 ``this/`` 前缀（``页面A`` → ``this/页面A``）。"""
    p = path.strip()
    if p.startswith("this/") or p.startswith("$this/"):
        return p
    if p in ("this", "$this") or p.startswith(("this", "$this")):
        return "this"
    return f"this/{p}"


def _iter_set_decls(text: str) -> list[tuple[str, str]]:
    """提取写入声明 ``(path, type)``（type ∈ TYPE_REGISTRY token/空串）。"""
    decls: list[tuple[str, str]] = []
    for m in _SET_TMPL.finditer(text):
        type_name = (m.group(1) or "").strip()
        path = _normalize_set_path(m.group(2) or "")
        if path and path != "this":
            decls.append((path, type_name))
    return decls


def _iter_get_paths(text: str) -> list[str]:
    """提取描述中的全部读取路径（``{{get:this/...}}``）。"""
    return [m.group(1).strip() for m in _GET_TMPL.finditer(text) if m.group(1).strip()]


def _iter_set_paths(text: str) -> list[str]:
    """提取描述中的全部写入路径（``{{set:...}}``）。"""
    return [path for path, _ in _iter_set_decls(text)]


def _iter_schema_paths(text: str) -> list[str]:
    """从自然语言描述中提取全部 ``this/...`` schema 路径（读引用/写声明/裸路径）。"""
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
    """``this/导出/username`` 或 ``$this/导出/username`` → ``('导出', 'username')``。

    兼容当前帧标记 ``this`` 与块绑定机制的旧标记 ``$this``；非法返回 None。
    """
    p = path.strip()
    for prefix in ("this/", "$this/"):
        if p.startswith(prefix):
            p = p[len(prefix) :]
            break
    else:
        if p in ("this", "$this") or p.startswith(("this", "$this")):
            return None
    parts = [s for s in p.split("/") if s]
    return tuple(parts) if parts else None


def _display_path(path: str) -> str:
    p = path.strip()
    if p.startswith(("this/", "$this/")):
        return p
    return f"this/{p}"


@dataclass
class ExpandContext:
    """展开期共享上下文：文档缓存、帧栈、绑定/帧记录、校验问题。"""

    ir: DocumentIR
    resolver: RefResolver
    max_depth: int
    stack: list[tuple[str, str]] = field(default_factory=list)
    bindings: list[ParamBinding] = field(default_factory=list)
    frames: list[FrameInfo] = field(default_factory=list)
    issues: list[CheckIssue] = field(default_factory=list)
    doc_cache: dict[str, DocumentIR] = field(default_factory=dict)
    children_cache: dict[tuple[str, str], frozenset[str]] = field(default_factory=dict)
    absent_docs: set[str] = field(default_factory=set)
    _doc_issues: dict[tuple[str, str, str], CheckIssue] = field(default_factory=dict)

    def add_issue(self, prefix: str, code: str, message: str, loc: Loc | None = None) -> None:
        self.issues.append(make_issue(prefix, code, message, loc))

    def direct_children(self, ir: DocumentIR, block_name: str) -> frozenset[str]:
        """块直接引用的块名集合（作为直接子帧的可见对象，§5.3.2）。"""
        key = (ir.doc_id, block_name)
        cached = self.children_cache.get(key)
        if cached is not None:
            return cached
        node = ir.ir_by_block.get(block_name)
        names = _collect_ref_blocks(node) if node is not None else frozenset()
        self.children_cache[key] = names
        return names

    def load_block(self, tdoc: str, tblock: str) -> tuple[DocumentIR, IRNode] | None:
        """加载目标块（本文档直接取；跨文档经 RefResolver 解析并缓存）。"""
        if tdoc == self.ir.doc_id:
            ir = self.ir
        elif tdoc in self.doc_cache:
            ir = self.doc_cache[tdoc]
        else:
            try:
                src = self.resolver.resolve(tdoc)
            except RefNotFoundError:
                self.absent_docs.add(tdoc)
                return None
            raw = normalize_document(src.data)
            st = document_mod.parse_structure(src, raw)
            self.doc_cache[tdoc] = st.ir
            for iss in st.issues:
                key = (iss.code, iss.message, iss.loc.path if iss.loc else "")
                if key not in self._doc_issues:
                    self._doc_issues[key] = iss
            ir = st.ir
        if tblock not in ir.ir_by_block:
            return None
        return ir, ir.ir_by_block[tblock]

    @property
    def resolved_doc_issues(self) -> list[CheckIssue]:
        return list(self._doc_issues.values())


@dataclass(frozen=True)
class ExpansionResult:
    """展开结果：基础节点树 + 绑定记录 + 命名空间帧 + 展开期校验问题。"""

    tree: Node
    bindings: tuple[ParamBinding, ...]
    frames: tuple[FrameInfo, ...]
    issues: tuple[CheckIssue, ...]


def _collect_ref_blocks(node: IRNode | None) -> frozenset[str]:
    """块自身 IR 中引用的块名集合（§5.3.2 直接子块可见范围）。"""
    if node is None:
        return frozenset()
    names: set[str] = set()
    if node.kind == "ref":
        target = node.ref_target or ""
        parts = [p for p in target.split("/") if p]
        if len(parts) == 2:
            names.add(parts[1])
        return frozenset(names)
    for child in node.children:
        names |= _collect_ref_blocks(child)
    for b in node.branches:
        if b.when is not None:
            names |= _collect_ref_blocks(b.when)
        if b.target is not None:
            names |= _collect_ref_blocks(b.target)
    for sub in (node.action, node.condition, node.until, node.body):
        if sub is not None:
            names |= _collect_ref_blocks(sub)
    return frozenset(names)


def expand_document(ctx: ExpandContext) -> ExpansionResult:
    """展开根块：基础节点树 + 绑定/帧记录 + 展开期校验问题。"""
    root = ctx.ir.root_block
    key = (ctx.ir.doc_id, root)
    children = ctx.direct_children(ctx.ir, root)
    root_path = f"{ctx.ir.doc_id}/"
    ctx.frames.append(
        FrameInfo(path=root_path, block=root, parent=None, children=tuple(sorted(children)))
    )
    ctx.stack.append(key)
    try:
        tree = _expand_ir(ctx.ir.root, ctx, root_path, children, 0)
    finally:
        ctx.stack.pop()
    return ExpansionResult(
        tree=tree,
        bindings=tuple(ctx.bindings),
        frames=tuple(ctx.frames),
        issues=tuple(ctx.issues),
    )


def _check_schema_path(
    ctx: ExpandContext, frame: str, children: frozenset[str], path_str: str, loc: Loc | None
) -> None:
    """变量契约校验：路径只指向自己的 schema 或直接子块 schema（§5.3.2）。"""
    display = _display_path(path_str)
    at = loc.path if loc else "?"
    segs = _schema_segments(path_str)
    if segs is None:
        ctx.add_issue(
            "scope",
            "out_of_scope",
            f"变量引用 '{display}' 非法（应为 this/变量 或 this/直接子块/变量，位于 {at}）",
            loc,
        )
        return
    if len(segs) == 1:
        return
    if len(segs) == 2:
        child = segs[0]
        if child in children:
            return
        ctx.add_issue(
            "scope",
            "out_of_scope",
            f"变量 '{display}' 指向非直接子块 '{child}'，越出本块可见作用域"
            f"（只可读/写自身与直接子块，位于 {at}）",
            loc,
        )
        return
    ctx.add_issue(
        "scope",
        "out_of_scope",
        f"变量 '{display}' 指向孙子/更深层级 schema，越出本块可见作用域（位于 {at}）",
        loc,
    )


def _scope_check_texts(
    ctx: ExpandContext,
    frame: str,
    children: frozenset[str],
    loc: Loc | None,
    *texts: str | None,
) -> None:
    for text in texts:
        if not text:
            continue
        for p in _iter_schema_paths(text):
            _check_schema_path(ctx, frame, children, p, loc)


def _expand_ir(
    node: IRNode,
    ctx: ExpandContext,
    frame: str,
    children: frozenset[str],
    depth: int,
) -> Node:
    if depth > ctx.max_depth:
        at = node.loc.path if node.loc else "?"
        ctx.add_issue(
            "expand",
            "depth_exceeded",
            f"展开嵌套过深（超过 {ctx.max_depth} 层上限，位于 {at}）",
            node.loc,
        )
        return SequenceNode(loc=node.loc, frame=frame)
    kind = node.kind
    rule = EXPANSION_RULES.get(kind)
    if rule is not None:
        return rule(node, ctx, frame, children, depth)
    if kind == "Action":
        _scope_check_texts(ctx, frame, children, node.loc, node.description)
        decls = _iter_set_decls(node.description or "")
        set_targets = tuple(_display_path(p) for p, _ in decls)
        set_decls = tuple((_display_path(p), t) for p, t in decls)
        return ActionNode(
            description=node.description or "",
            css_hint=node.css_hint,
            set_targets=set_targets,
            set_decls=set_decls,
            loc=node.loc,
            frame=frame,
        )
    if kind == "Condition":
        _scope_check_texts(
            ctx, frame, children, node.loc, node.description, node.target, node.predicate
        )
        return ConditionNode(
            description=node.description or "",
            target=node.target,
            predicate=node.predicate,
            loc=node.loc,
            frame=frame,
        )
    if kind == "Sequence":
        return SequenceNode(
            children=tuple(
                _expand_ir(c, ctx, frame, children, depth + 1) for c in node.children
            ),
            loc=node.loc,
            frame=frame,
        )
    if kind == "Selector":
        branches = tuple(
            BranchSpec(
                condition=(
                    _as_condition(_expand_ir(b.when, ctx, frame, children, depth + 1))
                    if b.when is not None
                    else None
                ),
                child=_expand_ir(b.target, ctx, frame, children, depth + 1),
            )
            for b in node.branches
        )
        return SelectorNode(branches=branches, loc=node.loc, frame=frame)
    if kind == "Repeat":
        body = _expand_ir(
            node.body or _empty_ir("Sequence", node.loc), ctx, frame, children, depth + 1
        )
        until = (
            _as_condition(_expand_ir(node.until, ctx, frame, children, depth + 1))
            if node.until is not None
            else None
        )
        return RepeatNode(
            body=body,
            mode=node.mode or "retry",
            until=until,
            max=node.max or 0,
            loc=node.loc,
            frame=frame,
        )
    if kind == "Finish":
        return FinishNode(loc=node.loc, frame=frame)
    if kind == "ref":
        return _expand_ref(node, ctx, frame, children, depth)
    return SequenceNode(loc=node.loc, frame=frame)


def _as_condition(node: Node) -> ConditionNode:
    """防御：将任意展开结果归一为 ConditionNode。"""
    if isinstance(node, ConditionNode):
        return node
    if isinstance(node, ActionNode):
        return ConditionNode(description=node.description, loc=node.loc, frame=node.frame)
    return ConditionNode(loc=node.loc, frame=node.frame)


def _empty_ir(kind: str, loc: Loc | None = None) -> IRNode:
    return IRNode(kind=kind, loc=loc)


def _rule_step(
    node: IRNode, ctx: ExpandContext, frame: str, children: frozenset[str], depth: int
) -> Node:
    """Step = Sequence(Action + Condition)。"""
    action = _expand_ir(
        node.action or _empty_ir("Action", node.loc), ctx, frame, children, depth + 1
    )
    cond = _expand_ir(
        node.condition or _empty_ir("Condition", node.loc), ctx, frame, children, depth + 1
    )
    return SequenceNode(children=(action, _as_condition(cond)), loc=node.loc, frame=frame)


def _rule_branch(
    node: IRNode, ctx: ExpandContext, frame: str, children: frozenset[str], depth: int
) -> Node:
    """Branch = Action + Selector（顺序检查 when，第一个命中生效，无匹配走 otherwise）。"""
    action = _expand_ir(
        node.action or _empty_ir("Action", node.loc), ctx, frame, children, depth + 1
    )
    branches = tuple(
        BranchSpec(
            condition=(
                _as_condition(_expand_ir(b.when, ctx, frame, children, depth + 1))
                if b.when is not None
                else None
            ),
            child=_expand_ir(b.target, ctx, frame, children, depth + 1),
        )
        for b in node.branches
    )
    selector = SelectorNode(branches=branches, loc=node.loc, frame=frame)
    return SequenceNode(children=(action, selector), loc=node.loc, frame=frame)


def _rule_loop_until(
    node: IRNode, ctx: ExpandContext, frame: str, children: frozenset[str], depth: int
) -> Node:
    """LoopUntil = Repeat(mode=loop_until, until=条件, max=上限)：每轮先判 until。"""
    action = _expand_ir(
        node.action or _empty_ir("Action", node.loc), ctx, frame, children, depth + 1
    )
    until = _as_condition(
        _expand_ir(
            node.until or _empty_ir("Condition", node.loc), ctx, frame, children, depth + 1
        )
    )
    return RepeatNode(
        body=action, mode="loop_until", until=until, max=node.max or 0, loc=node.loc, frame=frame
    )


def _rule_retry(
    node: IRNode, ctx: ExpandContext, frame: str, children: frozenset[str], depth: int
) -> Node:
    """Retry = Repeat(mode=retry, max=上限)：每轮后判 body 执行结果。"""
    body = _expand_ir(
        node.body or _empty_ir("Sequence", node.loc), ctx, frame, children, depth + 1
    )
    return RepeatNode(
        body=body, mode="retry", until=None, max=node.max or 0, loc=node.loc, frame=frame
    )


def _rule_if_then_else(
    node: IRNode, ctx: ExpandContext, frame: str, children: frozenset[str], depth: int
) -> Node:
    """IfThenElse = Selector(if→then, else→else)：先判 if 条件。"""
    cond = _as_condition(
        _expand_ir(
            node.condition or _empty_ir("Condition", node.loc), ctx, frame, children, depth + 1
        )
    )
    then_node = node.children[0] if node.children else None
    else_node = node.children[1] if len(node.children) > 1 else None
    then = _expand_ir(
        then_node or _empty_ir("Sequence", node.loc), ctx, frame, children, depth + 1
    )
    els = _expand_ir(
        else_node or _empty_ir("Sequence", node.loc), ctx, frame, children, depth + 1
    )
    return SelectorNode(
        branches=(
            BranchSpec(condition=cond, child=then),
            BranchSpec(condition=None, child=els),
        ),
        loc=node.loc,
        frame=frame,
    )


#: 复合节点展开规则映射（§4.3 精确语义，单一映射表，供表驱动测试直接覆盖）
EXPANSION_RULES: dict[str, Callable[[IRNode, ExpandContext, str, frozenset[str], int], Node]] = {
    "Step": _rule_step,
    "Branch": _rule_branch,
    "LoopUntil": _rule_loop_until,
    "Retry": _rule_retry,
    "IfThenElse": _rule_if_then_else,
}


def _expand_ref(
    node: IRNode, ctx: ExpandContext, frame: str, children: frozenset[str], depth: int
) -> Node:
    loc = node.loc
    at = loc.path if loc else "?"
    target = (node.ref_target or "").strip()
    parts = [p for p in target.split("/") if p]
    if len(parts) != 2:
        ctx.add_issue(
            "ref",
            "bad_syntax",
            f"ref 目标 '{target}' 语法错误（应为 'this/块名' 或 '文档名/块名'，位于 {at}）",
            loc,
        )
        return SequenceNode(loc=loc, frame=frame)
    tdoc = ctx.ir.doc_id if parts[0] == "this" else parts[0]
    tblock = parts[1]
    key = (tdoc, tblock)
    if key in ctx.stack:
        chain = " -> ".join(f"{d}/{b}" for d, b in [*ctx.stack, key])
        ctx.add_issue("ref", "cycle", f"检测到循环块引用: {chain}（位于 {at}）", loc)
        return SequenceNode(loc=loc, frame=frame)
    if len(ctx.stack) >= ctx.max_depth:
        ctx.add_issue(
            "ref",
            "recursion_depth",
            f"引用展开嵌套超过上限 {ctx.max_depth} 层（位于 {at}）",
            loc,
        )
        return SequenceNode(loc=loc, frame=frame)
    result = ctx.load_block(tdoc, tblock)
    if result is None:
        if tdoc in ctx.absent_docs:
            ctx.add_issue(
                "ref",
                "missing_doc",
                f"引用目标文档 '{tdoc}' 不存在（ref: {target}，位于 {at}）",
                loc,
            )
        else:
            ctx.add_issue(
                "ref",
                "missing_block",
                f"引用目标块 '{tdoc}/{tblock}' 不存在（ref: {target}，位于 {at}）",
                loc,
            )
        return SequenceNode(loc=loc, frame=frame)
    t_ir, t_node = result
    t_decl = t_ir.blocks.get(tblock)
    t_inputs = t_decl.inputs if t_decl is not None else ()
    bound_vars: set[str] = set()
    for tp, expr in node.bindings:
        segs = _schema_segments(tp)
        if segs is None or len(segs) != 2 or segs[0] != tblock:
            ctx.add_issue(
                "ref",
                "binding_target",
                f"绑定目标 '{tp}' 不属于被引用块 '{target}' 的 schema"
                f"（应为 $this/{tblock}/输入名，位于 {at}）",
                loc,
            )
        elif t_inputs and segs[1] not in t_inputs:
            ctx.add_issue(
                "ref",
                "binding_not_input",
                f"绑定目标 '{tp}' 不是块 '{tblock}' 声明的输入"
                f"（声明: {', '.join(t_inputs) or '无'}，位于 {at}）",
                loc,
            )
        else:
            bound_vars.add(segs[1])
        _check_schema_path(ctx, frame, children, tp, loc)
        _scope_check_texts(ctx, frame, children, loc, expr)
        ctx.bindings.append(
            ParamBinding(
                frame_path=frame, block_name=tblock, target_path=tp, value_expr=expr, loc=loc
            )
        )
    if t_inputs:
        missing = [v for v in t_inputs if v not in bound_vars]
        if missing:
            ctx.add_issue(
                "ref",
                "input_not_bound",
                f"引用 '{target}' 未绑定其声明输入: {', '.join(missing)}"
                f"（在 ref 处用 '写入' 注入，位于 {at}）",
                loc,
            )
    child_frame = f"{frame}{tblock}/"
    child_children = ctx.direct_children(t_ir, tblock)
    ctx.frames.append(
        FrameInfo(
            path=child_frame, block=tblock, parent=frame, children=tuple(sorted(child_children))
        )
    )
    ctx.stack.append(key)
    try:
        # ref 嵌套深度由 ctx.stack（调用栈帧语义）单独守护，不叠加到
        # 复合节点嵌套深度计数器（depth）上
        return _expand_ir(t_node, ctx, child_frame, child_children, depth)
    finally:
        ctx.stack.pop()
