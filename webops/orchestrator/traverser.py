"""M7 遍历器（design D1/D3/D4/D5/D6）：阻塞式 tick、组合节点聚合、帧同步与报告。

遍历器把全部基础节点统一为 ``tick`` 契约（返回 SUCCESS/FAILURE，无 RUNNING）：
- 组合节点（Sequence/Selector/Repeat/Finish）纯程序执行、按 §5.7.7 聚合短路；
- 叶子（Action/Condition）触发 M6（经注入的叶子执行器），接收 ``LeafResult``；
- 进入/退出块引用时同步 M3 schema 帧（design D4：建帧/释放）；
- 每个节点退出前记录 M8 报告、叶子返回前截图（§5.8.3）；
- 维护可查询执行状态（Reporter 内）与递归深度安全闸（design R1）。
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from webops.browser.errors import FatalBrowserError
from webops.browser.models import PageRef as BrowserPageRef
from webops.leaf_agent.models import LeafResult
from webops.orchestrator.context import RunContext
from webops.orchestrator.models import FAILURE, SUCCESS, NodeStatus, OrchestratorError
from webops.parser.models import (
    ActionNode,
    ConditionNode,
    FinishNode,
    Node,
    RepeatNode,
    SelectorNode,
    SequenceNode,
)
from webops.reporting.models import ActionCall, LeafTrace, NodeInfo, NodeReport
from webops.schema.errors import SchemaError

logger = logging.getLogger(__name__)

#: 递归栈深度安全闸（design R1；M2 解析已有展开深度上限，此处作运行期兜底）。
_MAX_RECURSION_DEPTH = 512


def node_type_name(node: Node) -> str:
    """节点类型名（M8 报告用）。"""
    if isinstance(node, ActionNode):
        return "Action"
    if isinstance(node, ConditionNode):
        return "Condition"
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


def count_nodes(node: Node) -> int:
    """统计树中基础节点总数（供 ``ExecState.progress`` 计算，design D3）。"""
    total = 1
    if isinstance(node, SequenceNode):
        for child in node.children:
            total += count_nodes(child)
    elif isinstance(node, SelectorNode):
        for branch in node.branches:
            if branch.condition is not None:
                total += count_nodes(branch.condition)
            total += count_nodes(branch.child)
    elif isinstance(node, RepeatNode):
        if node.until is not None:
            total += count_nodes(node.until)
        total += count_nodes(node.body)
    return total


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

        进入时把 schema 激活帧同步到节点所属帧（块引用建帧），退出时恢复
        （释放帧，无论成败，design D4）。运行期 ``SchemaError`` 捕获后按失败
        沿树传播（§5.7.7）；致命错误（``FatalBrowserError``）原样上抛。
        """
        self._check_depth()
        prev = self.ctx.current_frame.path if self.ctx.current_frame is not None else "/"
        self._sync_frame(node.frame)
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
            self._sync_frame(prev)
        return status

    # ------------------------------------------------------------ 节点分派

    def _dispatch(self, node: Node) -> NodeStatus:
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
        logger.warning("未知节点类型 %s（frame=%s）", type(node).__name__, node.frame)
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

        page_ref = self.ctx.space.current_page(self.ctx.current_frame)
        screenshot_path = ""
        if page_ref is not None:
            screenshot_path = self.ctx.reporter.capture_screenshot(
                BrowserPageRef(id=page_ref.page_id), node.description
            )
        report = NodeReport(
            node_type=node_type,
            node_desc=node.description,
            result="success" if status == SUCCESS else "failure",
            timestamp=_now_iso(),
            action_call=_primary_action_call(node, result),
            condition_result=result.bool_value if isinstance(node, ConditionNode) else None,
            page_url=page_ref.url if page_ref is not None else None,
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

    # ------------------------------------------------------------ schema 帧

    def _sync_frame(self, target: str) -> None:
        """把 schema 激活帧同步到节点帧路径（进入/退出块帧，LIFO 严格匹配）。

        ``enter_block`` 携带块声明的配置覆盖（design D4），``exit_block`` 恢复
        父帧为激活帧（释放 = 退出激活栈，帧数据保留供父块读输出）。
        """
        space = self.ctx.space
        current = space._current
        while current is not None and current.path != target:
            if target.startswith(current.path):
                segment = target[len(current.path):].strip("/").split("/", 1)[0]
                if not segment:
                    raise OrchestratorError(f"节点帧路径非法: {target!r}")
                space.enter_block(segment, self.ctx.schema_decl(segment))
            elif current.parent is None:
                raise OrchestratorError(
                    f"节点帧路径 {target!r} 与当前 schema 帧链不匹配（已达根帧）"
                )
            else:
                space.exit_block()
            current = space._current
        if current is None:
            raise OrchestratorError(f"节点帧路径 {target!r} 无法匹配（schema 帧已全部释放）")

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
        loc = node.loc.path if node.loc is not None else node.frame
        self.ctx.failure_reason = (
            f"{node_type_name(node)}『{node_desc(node)}』失败: {text}（位于 {loc}）"
        )

    def _check_depth(self) -> None:
        if self._depth >= _MAX_RECURSION_DEPTH:
            raise OrchestratorError(f"遍历嵌套过深（超过 {_MAX_RECURSION_DEPTH} 层）")


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
