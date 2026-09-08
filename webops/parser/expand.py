"""复合节点展开与块引用解析（设计决策 D1 第二阶段，任务 3.x/4.x/5.x 展开期）。

在中间表示之上执行：

- 复合节点展开（§4.3 精确语义，规则集中于 ``EXPANSION_RULES`` 单一映射表）
- 块引用解析（``this/块名``、``文档名/块名`` 跨文档整树）与循环引用检测、
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

from webops.parser import document as document_mod
from webops.parser.document import DocumentIR, IRNode
from webops.parser.errors import RefNotFoundError
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
from webops.parser.refs import RefResolver
from webops.parser.yamlio import normalize_document

#: ``[[get:this/path]]`` 读取引用（叶子执行前程序替换为真实值）
_GET_TMPL = re.compile(r"\[\[\s*get:\s*this/([^\[\]]+?)\s*\]\]")
#: ``[[set[:type]:path]]`` 写入声明；type ∈ TYPE_REGISTRY token（可省略），path 可带 this/ 或不带
_SET_TMPL = re.compile(
    r"\[\[\s*set:(?:(str|int|float|bool|page_ref):)?\s*((?:this/)?[^\[\]:]+?)\s*\]\]"
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
    """提取描述中的全部读取路径（``[[get:this/...]]``）。"""
    return [m.group(1).strip() for m in _GET_TMPL.finditer(text) if m.group(1).strip()]


def _iter_set_paths(text: str) -> list[str]:
    """提取描述中的全部写入路径（``[[set:...]]``）。"""
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
    """剥掉 ``this/`` 前缀后的路径段（如 ``this/username`` → ``('username',)``）。

    兼容旧标记 ``$this``（仅内部归一化）；非法返回 None。函数式传参后
    用户层只用单段 ``this/<名>``。
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
    """展开期共享上下文：文档缓存、校验问题。"""

    ir: DocumentIR
    resolver: RefResolver
    max_depth: int
    issues: list[CheckIssue] = field(default_factory=list)
    doc_cache: dict[str, DocumentIR] = field(default_factory=dict)
    absent_docs: set[str] = field(default_factory=set)
    _doc_issues: dict[tuple[str, str, str], CheckIssue] = field(default_factory=dict)

    def add_issue(self, prefix: str, code: str, message: str, loc: Loc | None = None) -> None:
        self.issues.append(make_issue(prefix, code, message, loc))

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
    """展开结果：根块基础树 + 每块预展开树 + 展开期校验问题。"""

    tree: Node
    blocks_tree: dict[str, Node]
    issues: tuple[CheckIssue, ...]


def expand_document(ctx: ExpandContext) -> ExpansionResult:
    """对每块独立预展开为基础树；根块树 = ``tree``，全部块树存入 ``blocks_tree``。

    遍历顺序：先根文档全部命名块，再跨文档缓存（``doc_cache``）中陆续加载的
    文档全部命名块，直至无新文档。随后做跨块 ref 图的静态环/深度检测与声明级
    output 全赋值校验。
    """
    blocks_tree: dict[str, Node] = {}
    root_block = ctx.ir.root_block
    seen_docs: set[str] = set()
    while True:
        pending = [ir for ir in _all_docs(ctx) if ir.doc_id not in seen_docs]
        if not pending:
            break
        for ir in pending:
            seen_docs.add(ir.doc_id)
            for block_name in ir.ir_by_block:
                tree = _expand_block_ir(ir, block_name, ctx)
                if block_name not in blocks_tree:
                    blocks_tree[block_name] = tree
                else:
                    blocks_tree[f"{ir.doc_id}/{block_name}"] = tree
    root_tree = blocks_tree[root_block]
    _check_ref_graph(ctx, blocks_tree)
    _check_all_block_outputs(ctx)
    return ExpansionResult(
        tree=root_tree,
        blocks_tree=blocks_tree,
        issues=tuple(ctx.issues),
    )


def _expand_block_ir(ir: DocumentIR, block_name: str, ctx: ExpandContext) -> Node:
    """对单块 IR 展开为基础树（不含 ref 内联；遇 ref 生成 ``RefNode``）。"""
    node = ir.ir_by_block.get(block_name)
    if node is None:
        return SequenceNode(loc=None)
    return _expand_ir(node, ctx, 0)


def _all_docs(ctx: ExpandContext) -> list[DocumentIR]:
    """当前文档 + 展开期跨文档缓存（供逐块预展开与声明级 output 校验遍历）。"""
    docs = [ctx.ir]
    docs.extend(ctx.doc_cache.values())
    return docs


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
        for _out_name, target_var in node.returns:
            segs = _schema_segments(target_var)
            if segs is not None and len(segs) == 1:
                names.add(segs[0])
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


def _check_all_block_outputs(ctx: ExpandContext) -> None:
    """声明级 output 全赋值校验（§4）：每个声明的输出名须在块体内有赋值点。"""
    for ir in _all_docs(ctx):
        for block_name, decl in ir.blocks.items():
            if not decl.outputs:
                continue
            node = ir.ir_by_block.get(block_name)
            assigned = _collect_output_assignment_names(node)
            for out in decl.outputs:
                if out in assigned:
                    continue
                at = (
                    f"{ir.doc_id}/{block_name}"
                    if node is None or node.loc is None
                    else node.loc.path
                )
                ctx.add_issue(
                    "ref",
                    "output_not_set",
                    f"块 '{block_name}' 声明的输出 '{out}' 在块体内未赋值"
                    f"（需叶子 [[set:...:this/{out}]] 或 ref 的 returns 目标，位于 {at}）",
                    node.loc if node is not None else None,
                )


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
    """ref 保留为 ``RefNode``（不再内联）：静态校验 + 返回调用节点。

    静态校验：目标语法/存在性、args⊆inputs、inputs 全必填、returns⊆outputs、
    实参与 returns 目标作用域单段。环/深度检测在 ``_check_ref_graph`` 中
    跨 ``blocks_tree`` 的 ref 图统一走查（本函数不再递归展开目标块）。
    """
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
        return SequenceNode(loc=loc)
    tdoc = ctx.ir.doc_id if parts[0] == "this" else parts[0]
    tblock = parts[1]
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
        return SequenceNode(loc=loc)
    _t_ir, _t_node = result
    t_decl = _t_ir.blocks.get(tblock)
    t_inputs = t_decl.inputs if t_decl is not None else ()
    t_outputs = t_decl.outputs if t_decl is not None else ()
    input_names = {n for n, _ in t_inputs}
    bound_vars: set[str] = set()
    # args：实参表达式（裸路径 this/<名> 或字面量）
    for arg_name, expr in node.args:
        if arg_name not in input_names:
            ctx.add_issue(
                "ref",
                "args_not_input",
                f"实参 '{arg_name}' 不是块 '{tblock}' 声明的输入"
                f"（声明: {', '.join(sorted(input_names)) or '无'}，位于 {at}）",
                loc,
            )
        else:
            bound_vars.add(arg_name)
        _scope_check_texts(ctx, loc, expr)
    # inputs 全必填
    missing = [n for n, _ in t_inputs if n not in bound_vars]
    if missing:
        ctx.add_issue(
            "ref",
            "input_not_bound",
            f"引用 '{target}' 未绑定其声明输入: {', '.join(missing)}"
            f"（在 ref 处用 args 传实参，位于 {at}）",
            loc,
        )
    # returns：接收输出 → 本帧局部变量
    for out_name, target_var in node.returns:
        if out_name not in t_outputs:
            ctx.add_issue(
                "ref",
                "returns_not_output",
                f"返回值 '{out_name}' 不是块 '{tblock}' 声明的输出"
                f"（声明: {', '.join(t_outputs) or '无'}，位于 {at}）",
                loc,
            )
        _check_schema_path(ctx, target_var, loc)
    return RefNode(ref_target=target, args=node.args, returns=node.returns, loc=loc)


def _find_block_tree(
    blocks_tree: dict[str, Node], tdoc: str, tblock: str
) -> Node | None:
    """按 ``blocks_tree`` 定位块树：优先 ``文档/块`` 键（跨文档同名块），
    否则按纯块名（``this/`` 同文档引用与单文档场景）。"""
    qualified = blocks_tree.get(f"{tdoc}/{tblock}")
    if qualified is not None:
        return qualified
    return blocks_tree.get(tblock)


def _check_ref_graph(ctx: ExpandContext, blocks_tree: dict[str, Node]) -> None:
    """静态环/深度检测：沿根块可达的 ref 图走查（跨 ``blocks_tree``）。

    与旧内联展开语义一致：只检查从根块可达的引用链；``path`` 即调用链
    （栈语义，进入/退出各自拷贝），遇已在链上的目标块 → ``ref.cycle``；
    链长达到上限 → ``ref.recursion_depth``。
    """
    root_tree = blocks_tree.get(ctx.ir.root_block)
    if root_tree is None:
        return
    path = [(ctx.ir.doc_id, ctx.ir.root_block)]
    _walk_ref_edges(ctx, blocks_tree, root_tree, path)


def _walk_ref_edges(
    ctx: ExpandContext, blocks_tree: dict[str, Node], node: Node, path: list[tuple[str, str]]
) -> None:
    """DFS 走查块树内全部 ref 边；遇 RefNode 校验环/深度后进入目标块树。"""
    if isinstance(node, RefNode):
        target = (node.ref_target or "").strip()
        parts = [p for p in target.split("/") if p]
        if len(parts) != 2:
            return
        tdoc = ctx.ir.doc_id if parts[0] == "this" else parts[0]
        tblock = parts[1]
        key = (tdoc, tblock)
        at = node.loc.path if node.loc else "?"
        if key in path:
            chain = " -> ".join(f"{d}/{b}" for d, b in [*path, key])
            ctx.add_issue("ref", "cycle", f"检测到循环块引用: {chain}（位于 {at}）", node.loc)
            return
        if len(path) >= ctx.max_depth:
            ctx.add_issue(
                "ref",
                "recursion_depth",
                f"引用展开嵌套超过上限 {ctx.max_depth} 层（位于 {at}）",
                node.loc,
            )
            return
        child = _find_block_tree(blocks_tree, tdoc, tblock)
        if child is not None:
            _walk_ref_edges(ctx, blocks_tree, child, [*path, key])
        return
    if isinstance(node, SequenceNode):
        for c in node.children:
            _walk_ref_edges(ctx, blocks_tree, c, path)
    elif isinstance(node, SelectorNode):
        for b in node.branches:
            if b.condition is not None:
                _walk_ref_edges(ctx, blocks_tree, b.condition, path)
            _walk_ref_edges(ctx, blocks_tree, b.child, path)
    elif isinstance(node, RepeatNode):
        if node.until is not None:
            _walk_ref_edges(ctx, blocks_tree, node.until, path)
        _walk_ref_edges(ctx, blocks_tree, node.body, path)
