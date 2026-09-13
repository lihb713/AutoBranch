"""M7 遍历器（design D1/D3/D4/D5/D6）：阻塞式 tick、组合节点聚合、ref 动态调用与报告。

遍历器把全部基础节点统一为 ``tick`` 契约（返回 SUCCESS/FAILURE，无 RUNNING）：
- 组合节点（Sequence/Selector/Repeat/Finish）纯程序执行、按 §5.7.7 聚合短路；
- 叶子（Action/Condition）触发 M6（经注入的叶子执行器），接收 ``LeafResult``；
- ref（``RefNode``）运行时动态调用：建子帧 → 注入实参 → 递归执行目标块树 →
  回收 returns 到父帧 → 退出子帧（帧由 ``_tick_ref`` 管理，无静态 frame 同步）；
- 每个节点退出前记录 M8 报告、叶子返回前截图（§5.8.3）；
- 维护可查询执行状态（Reporter 内）与递归深度安全闸（design R1）。
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from webops.browser.errors import FatalBrowserError
from webops.leaf_agent.models import LeafResult
from webops.orchestrator.context import RunContext
from webops.orchestrator.models import FAILURE, SUCCESS, NodeStatus, OrchestratorError
from webops.parser.models import (
    ActionNode,
    ConditionNode,
    FinishNode,
    Node,
    RefNode,
    RepeatNode,
    SelectorNode,
    SequenceNode,
)
from webops.reporting.models import ActionCall, LeafTrace, NodeInfo, NodeReport
from webops.schema import FrameDecl
from webops.schema.errors import SchemaError
from webops.schema.path import resolve_target
from webops.schema.types import coerce, infer_type

logger = logging.getLogger(__name__)

#: 递归栈深度安全闸（design R1；M2 解析已有展开深度上限，此处作运行期兜底）。
_MAX_RECURSION_DEPTH = 512


def node_type_name(node: Node) -> str:
    """节点类型名（M8 报告用）。"""
    if isinstance(node, ActionNode):
        return "Action"
    if isinstance(node, ConditionNode):
        return "Condition"
    if isinstance(node, RefNode):
        return "Ref"
    if isinstance(node, SequenceNode):
        return "Sequence"
    if isinstance(node, SelectorNode):
        return "Selector"
    if isinstance(node, RepeatNode):
        return "Repeat"
    if isinstance(node, FinishNode):
        return "Finish"
    return type(node).__name__


def node_desc(node: Node) -> str:
    """节点描述：叶子取自然语言描述，组合节点取类型名。"""
    if isinstance(node, (ActionNode, ConditionNode)):
        return node.description
    return node_type_name(node)


def count_nodes(
    node: Node,
    blocks_tree: dict[str, Node] | None = None,
    _seen: set[str] | None = None,
    resolver=None,
) -> int:
    """统计树中基础节点总数（供 ``ExecState.progress`` 计算，design D3）。

    ``RefNode`` 计 1，并递归计入其被引用文档树（经 resolver 加载；无
    resolver 时回退 ``blocks_tree``）。运行期 ``_tick_ref`` 递归 tick 被引
    文档并逐节点记录，故 total 必须同样计入，否则 completed/total 提前
    超 1、进度饱和到 1.0。ref 图静态已保证 DAG，此处 ``_seen`` 作防御性
    环保护。
    """
    total = 1
    if isinstance(node, RefNode):
        target = (node.ref_target or "").strip()
        child = None
        if target and "/" not in target:
            if resolver is not None:
                child = _load_doc_tree_for_count(resolver, target)
            elif blocks_tree is not None:
                child = blocks_tree.get(target)
        if child is not None:
            key = target
            if _seen is None:
                _seen = set()
            if key not in _seen:
                _seen.add(key)
                total += count_nodes(child, blocks_tree, _seen, resolver)
    elif isinstance(node, SequenceNode):
        for child in node.children:
            total += count_nodes(child, blocks_tree, _seen, resolver)
    elif isinstance(node, SelectorNode):
        for branch in node.branches:
            if branch.condition is not None:
                total += count_nodes(branch.condition, blocks_tree, _seen, resolver)
            total += count_nodes(branch.child, blocks_tree, _seen, resolver)
    elif isinstance(node, RepeatNode):
        if node.until is not None:
            total += count_nodes(node.until, blocks_tree, _seen, resolver)
        total += count_nodes(node.body, blocks_tree, _seen, resolver)
    return total


def _load_doc_tree_for_count(resolver, doc_id: str):
    """经 resolver 加载被引文档并展开其主树（仅进度计数用，不执行）。"""
    try:
        from webops.parser.expand import ExpandContext, expand_document
        from webops.parser.onedoc import parse_document as parse_onedoc

        src = resolver.resolve(doc_id)
        ores = parse_onedoc(src, resolver)
        if not ores.checks_ok() or ores.main_tree is None:
            return None
        ectx = ExpandContext(max_depth=64)
        return expand_document(ores.main_tree, ectx, decl_inputs=ores.decl_inputs).tree
    except Exception:
        return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Traverser:
    """确定性阻塞式遍历器（契约 §5.7.7）。

    :param ctx: 运行上下文（依赖注入，mock 友好）。
    """

    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx
        self._depth = 0

    # ------------------------------------------------------------ tick 契约

    def tick(self, node: Node) -> NodeStatus:
        """节点统一 tick：返回 SUCCESS/FAILURE（阻塞式，无 RUNNING）。

        帧由运行时动态管理：``RefNode`` 经 ``_tick_ref`` 建子帧/退出子帧；
        其余节点共享所在块帧，不做帧切换。运行期 ``SchemaError`` 捕获后按失败
        沿树传播（§5.7.7）；致命错误（``FatalBrowserError``）原样上抛。
        """
        self._check_depth()
        self._depth += 1
        self._start_node(node)
        status: NodeStatus = FAILURE
        try:
            try:
                status = self._dispatch(node)
            except SchemaError as exc:
                self._note_failure(node, f"运行期 schema 错误: {exc}")
                status = FAILURE
        finally:
            if not isinstance(node, (ActionNode, ConditionNode)):
                self._record_node(node, status)
            self._depth -= 1
        return status

    # ------------------------------------------------------------ 节点分派

    def _dispatch(self, node: Node) -> NodeStatus:
        if isinstance(node, RefNode):
            return self._tick_ref(node)
        if isinstance(node, (ActionNode, ConditionNode)):
            return self._tick_leaf(node)
        if isinstance(node, SequenceNode):
            return self._tick_sequence(node)
        if isinstance(node, SelectorNode):
            return self._tick_selector(node)
        if isinstance(node, RepeatNode):
            return self._tick_repeat(node)
        if isinstance(node, FinishNode):
            return self._tick_finish(node)
        self._note_failure(node, f"未知节点类型: {type(node).__name__}")
        logger.warning("未知节点类型 %s", type(node).__name__)
        return FAILURE

    def _tick_sequence(self, node: SequenceNode) -> NodeStatus:
        """Sequence：依次执行，首个 FAILURE 短路 → 整体 FAILURE；全 SUCCESS → SUCCESS。"""
        for child in node.children:
            if self.tick(child) == FAILURE:
                return FAILURE
        return SUCCESS

    def _tick_selector(self, node: SelectorNode) -> NodeStatus:
        """Selector：按条件分流，首个命中分支生效（短路）；全 FAILURE → FAILURE。

        分支条件（``condition``）先判：FAILURE 则试下一分支；SUCCESS（或
        otherwise 无条件分支）即执行该分支子节点，其结果即 Selector 结果
        （不承载兜底，命中后不再检查其余分支）。
        """
        for branch in node.branches:
            if branch.condition is not None and self.tick(branch.condition) == FAILURE:
                continue
            return self.tick(branch.child)
        return FAILURE

    def _tick_repeat(self, node: RepeatNode) -> NodeStatus:
        """Repeat：循环带上限；到达上限仍未满足退出条件 → 整体 FAILURE。"""
        if node.max <= 0:
            return FAILURE
        if node.mode == "loop_until":
            return self._tick_loop_until(node)
        return self._tick_retry(node)

    def _tick_loop_until(self, node: RepeatNode) -> NodeStatus:
        """LoopUntil：每轮先判 until（页面条件），满足即退；不满足才执行 body。"""
        for _ in range(node.max):
            if node.until is None:
                self._note_failure(node, "loop_until 缺少 until 条件")
                return FAILURE
            if self.tick(node.until) == SUCCESS:
                return SUCCESS
            if self.tick(node.body) == FAILURE:
                return FAILURE
        return FAILURE

    def _tick_retry(self, node: RepeatNode) -> NodeStatus:
        """Retry：每轮直接执行 body，成功即退；失败重试至 max 上界。"""
        for _ in range(node.max):
            if self.tick(node.body) == SUCCESS:
                return SUCCESS
        return FAILURE

    def _tick_finish(self, node: FinishNode) -> NodeStatus:
        """Finish：完成/终止（报告节点，纯程序），恒为 SUCCESS。"""
        return SUCCESS

    # ------------------------------------------------------------ 叶子触发

    def _tick_leaf(self, node: ActionNode | ConditionNode) -> NodeStatus:
        """Action/Condition 叶子：触发 M6 执行、接收 ``LeafResult``，返回前截图。"""
        node_type = "Action" if isinstance(node, ActionNode) else "Condition"
        timeout = self._effective_timeout()
        result, elapsed = self._execute_leaf(node, timeout)
        timed_out = timeout is not None and elapsed > timeout

        status: NodeStatus = FAILURE
        if not timed_out and result.status == "success":
            status = SUCCESS
        if status == FAILURE:
            self._note_failure(node, _leaf_failure_text(node_type, result, timed_out, timeout))

        page_ref = self.ctx.browser.current_page()
        screenshot_path = ""
        page_url = None
        if page_ref is not None:
            page_result = self.ctx.browser.page(page_ref)
            if page_result.ok:
                handle = page_result.detail["page"]
                page_url = handle.url
                screenshot_path = self.ctx.reporter.capture_screenshot(page_ref, node.description)
        report = NodeReport(
            node_type=node_type,
            node_desc=node.description,
            result="success" if status == SUCCESS else "failure",
            timestamp=_now_iso(),
            action_call=_primary_action_call(node, result),
            condition_result=result.bool_value if isinstance(node, ConditionNode) else None,
            page_url=page_url,
            screenshot_path=screenshot_path or None,
            llm_trace=result.trace,
        )
        self.ctx.reporter.record_node(report)
        return status

    def _execute_leaf(self, node: Node, timeout: float | None) -> tuple[LeafResult, float]:
        """触发叶子执行；普通异常包装为程序侧失败，致命错误上抛。"""
        try:
            start = time.monotonic()
            result = self.ctx.leaf_executor(node, timeout)
            return result, time.monotonic() - start
        except FatalBrowserError:
            raise
        except Exception as exc:
            logger.warning("叶子执行抛出未预期异常（%s）: %s", node_desc(node), exc)
            trace = LeafTrace(
                llm_input={
                    "node_type": node_type_name(node),
                    "node_desc": node_desc(node),
                    "error": str(exc),
                }
            )
            return LeafResult(status="failure", error_source="program", trace=trace), 0.0

    def _effective_timeout(self) -> float | None:
        """节点生效超时：``resolve_config('timeout')``（自身 → 祖先 → 全局默认）。"""
        frame = self.ctx.current_frame
        if frame is None:
            return None
        value = self.ctx.space.resolve_config(frame, "timeout")
        if value is None:
            return None
        return float(value)

    # ------------------------------------------------------------ ref 动态调用

    def _tick_ref(self, node: RefNode) -> NodeStatus:
        """ref 运行时动态调用（一文档一树）：加载被引文档 → 从其 Root 执行。

        执行顺序（§3 执行模型）：
        1. 经 resolver 按文档名加载被引文档，解析其主树与文档级声明。
        2. 求值每个实参（``this/<名>``/裸变量名读父帧；非变量按字面量），
           按序对应被引文档 ``inputs``；coerce 到声明类型。
        3. ``enter_frame`` 建子帧，cast 后形参写入子帧（``this/形参名``）。
        4. 递归 ``tick`` 被引文档主树（从 Root 执行；其内部 ref 由各自 _tick_ref 管理）。
        5. 被引树 SUCCESS → 按 ``returns``（按序对应 ``outputs``）读子帧输出
           写父帧局部变量；FAILURE → 不写 returns，失败向上传播。
        6. ``exit_frame`` 退出子帧（数据保留至 run 结束）。
        """
        target = (node.ref_target or "").strip()
        if not target or "/" in target:
            msg = f"ref 目标非法（应为文档名单段）: {target!r}"
            return self._note_failure(node, msg) or FAILURE
        loaded = self._load_doc_tree(target)
        if loaded is None:
            return self._note_failure(node, f"引用文档不存在或无法解析: {target!r}") or FAILURE
        child_tree, decl = loaded
        space = self.ctx.space
        parent = self.ctx.current_frame
        input_types = dict(decl.inputs) if decl else {}
        input_names = list(input_types)
        # 2) 求值 args（按序对应 inputs）：变量读父帧；非变量按字面量
        args_values: dict[str, object] = {}
        if len(node.args) != len(input_names):
            return (
                self._note_failure(
                    node,
                    f"实参数量 {len(node.args)} 与被引文档 '{target}' "
                    f"入参数量 {len(input_names)} 不符",
                )
                or FAILURE
            )
        for i, expr in enumerate(node.args):
            name = input_names[i]
            val = self._eval_arg(parent, expr)
            if val is _MISSING:
                return (
                    self._note_failure(node, f"实参 '{expr!r}' 求值失败（变量未定义）")
                    or FAILURE
                )
            args_values[name] = val
        # coerce 到输入类型
        typed: dict[str, object] = {}
        for name, val in args_values.items():
            t = input_types.get(name, "")
            typed[name] = coerce(t, val) if t else val
        # 3) 建子帧（注入 inputs/config）
        frame = None
        try:
            frame = space.enter_frame(target, decl)
            for name, val in typed.items():
                space.write(
                    frame, f"this/{name}", val, input_types.get(name, "") or infer_type(val)
                )
            # 4) 递归执行被引文档主树（从 Root 执行）
            status = self.tick(child_tree)
            # 5) SUCCESS → returns 回收写父帧（按序对应 outputs）
            if status == SUCCESS:
                out_names = list(decl.outputs) if decl else []
                for i, (recv_name, _typ) in enumerate(node.returns):
                    if i >= len(out_names):
                        continue
                    value = space.read(frame, f"this/{out_names[i]}")  # 子帧读输出
                    if value is not None:
                        declared = (
                            parent.declared.get(recv_name)
                            or parent.outputs.get(recv_name)
                            or parent.inputs.get(recv_name)
                        )
                        space.write(
                            parent,
                            f"this/{recv_name}",
                            value,
                            declared or _typ or infer_type(value),
                        )
        finally:
            if frame is not None:
                # 6) 退出子帧（数据保留至 run 结束）
                space.exit_frame()
        return status

    def _load_doc_tree(self, doc_id: str) -> tuple[Node, object] | None:
        """经 resolver 加载被引文档，解析其主树与文档级声明（供 ref 执行）。"""
        resolver = self.ctx.resolver
        if resolver is None:
            return None
        try:
            src = resolver.resolve(doc_id)
        except Exception:
            return None
        try:
            from webops.parser.onedoc import parse_document as parse_onedoc

            ores = parse_onedoc(src, resolver)
        except Exception:
            return None
        if not ores.checks_ok() or ores.main_tree is None:
            return None
        from webops.parser.expand import ExpandContext, expand_document

        ectx = ExpandContext(max_depth=64)
        expansion = expand_document(ores.main_tree, ectx, decl_inputs=ores.decl_inputs)
        decl = FrameDecl(
            name=doc_id,
            inputs=dict(ores.decl_inputs),
            outputs={name: "" for name in ores.decl_outputs},
            config=dict(ores.config),
        )
        return expansion.tree, decl

    def _eval_arg(self, frame, expr: str):
        """求值实参表达式：``this/<名>`` 或裸名（父帧已有变量）→ 读父帧；
        否则视为字面量。

        未定义（父帧从未写入该变量）返回 ``_MISSING`` 哨兵，由调用方判失败；
        已定义（即便值为 None）返回存储值原样。``space.read`` 对未定义与
        已存 None 均返回 None，故先经 ``resolve_target``/storage 判定存在性。
        """
        if _single_segment(expr) is not None:
            target, var = resolve_target(frame, expr)
            if var not in target.storage:
                return _MISSING
            return self.ctx.space.read(frame, expr)
        if expr in frame.storage:
            return self.ctx.space.read(frame, f"this/{expr}")
        return _parse_literal(expr)

    # ------------------------------------------------------------ 报告与状态

    def _start_node(self, node: Node) -> None:
        self.ctx.reporter.start_node(
            NodeInfo(node_type=node_type_name(node), node_desc=node_desc(node))
        )

    def _record_node(self, node: Node, status: NodeStatus) -> None:
        self.ctx.reporter.record_node(
            NodeReport(
                node_type=node_type_name(node),
                node_desc=node_desc(node),
                result="success" if status == SUCCESS else "failure",
                timestamp=_now_iso(),
            )
        )

    def _note_failure(self, node: Node, text: str) -> None:
        """记录首个失败节点描述（根统一终止时的失败原因，指向失败叶子）。"""
        if self.ctx.failure_reason is not None:
            return
        loc = node.loc.path if node.loc is not None else "?"
        self.ctx.failure_reason = (
            f"{node_type_name(node)}『{node_desc(node)}』失败: {text}（位于 {loc}）"
        )

    def _check_depth(self) -> None:
        if self._depth >= _MAX_RECURSION_DEPTH:
            raise OrchestratorError(f"遍历嵌套过深（超过 {_MAX_RECURSION_DEPTH} 层）")


#: 实参求值失败哨兵（与有效值区分；None 是合法存储值）。
_MISSING = object()


def _single_segment(path: str) -> str | None:
    """取单段裸路径 ``this/<名>`` 的 ``<名>``；其余形式（跨段/字面量）返回 None。"""
    parts = [p for p in (path or "").strip().split("/") if p]
    if len(parts) == 2 and parts[0] == "this":
        return parts[1]
    return None


def _parse_literal(expr: str):
    """把字面量表达式转成基础值（str/int/float/bool），无法转换按原字符串。"""
    s = (expr or "").strip()
    lowered = s.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _leaf_failure_text(
    node_type: str, result: LeafResult, timed_out: bool, timeout: float | None
) -> str:
    """叶子失败原因文本（供 ``failure_reason`` 展示）。"""
    if timed_out:
        return f"执行超时（>{timeout} 秒）"
    if result.error_source == "program":
        term = result.trace.terminator or "程序侧失败"
        return f"程序侧失败（{term}）"
    term = result.trace.terminator or "LLM 侧失败"
    return f"LLM 侧失败（{term}）"


def _primary_action_call(node: Node, result: LeafResult) -> ActionCall | None:
    """Action 专有：从执行追踪的首个工具调用派生 ``ActionCall``（无则 None）。"""
    if not isinstance(node, ActionNode):
        return None
    calls = result.trace.calls
    if not calls:
        return None
    first = calls[0]
    return ActionCall(
        function=first.name,
        success=bool(first.success),
        arguments=first.arguments,
        error=None,
    )


__all__ = [
    "Traverser",
    "node_type_name",
    "node_desc",
    "count_nodes",
    "NodeStatus",
]
