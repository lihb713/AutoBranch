"""M8 报告机制数据契约（M8 spec §5.1/§5.2/§5.3、契约 §5.8.3/§12.4）。

- ``NodeReport``：单节点执行报告（契约 §5.8.3），Action/Condition/复合节点
  差异用「字段 + 可空专有字段」承载（设计决策 2）。
- ``ActionCall``：Action 专有的引擎函数调用记录。
- ``LeafTrace``：叶子节点调用 LLM 的推理追踪数据，供回溯报告（报告②）。
  本模块按 M6 spec §5.1 的 ``LeafTrace`` 独立定义该数据契约，不依赖 M6 实现。
- ``ExecState``：可查询执行状态（契约 §12.4），``progress`` 由完成节点数与
  总节点数派生（设计决策 3，单数据源）。
- ``ExecReport`` / ``TraceReport`` / ``ReportBundle``：两份报告与打包结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

NodeResult = Literal["success", "failure"]


@dataclass(frozen=True)
class ActionCall:
    """Action 节点调用过的引擎函数记录（M8 spec §5.1）。

    :param function: 调用的引擎函数名。
    :param success: 该次调用是否成功。
    :param arguments: 调用参数（可选）。
    :param error: 调用失败原因（可选）。
    """

    function: str
    success: bool
    arguments: dict[str, Any] | None = None
    error: str | None = None


@dataclass(frozen=True)
class ToolCallRecord:
    """LLM 单次工具调用记录（``LeafTrace.calls`` 元素，M6 spec §5.1）。"""

    name: str
    arguments: dict[str, Any] | None = None
    result: str | None = None
    success: bool | None = None


@dataclass(frozen=True)
class LeafTrace:
    """叶子节点调用 LLM 的推理追踪数据（供回溯报告，契约 §5.8.3 报告②）。

    覆盖「提供给 LLM 的输入 / LLM 的推理过程 / LLM 的决策结果」，并保留
    M6 ``LeafTrace`` 的工具调用序列（calls）与终止条件（terminator）字段。
    """

    llm_input: dict[str, Any]
    llm_reasoning: list[Any] = field(default_factory=list)
    decision: str | None = None
    calls: list[ToolCallRecord] = field(default_factory=list)
    terminator: str | None = None


@dataclass(frozen=True)
class NodeReport:
    """单节点执行报告（M8 spec §5.1、契约 §5.8.3）。

    :param node_type: 节点类型（Action/Condition/Sequence/...）。
    :param node_desc: 节点描述。
    :param result: 执行结果（success/failure）。
    :param timestamp: 记录时间。
    :param action_call: Action 专有；非 Action 节点为 ``None``。
    :param condition_result: Condition 专有；非 Condition 节点为 ``None``。
    :param page_url: 节点执行时的页面 URL。
    :param screenshot_path: Action/Condition 专有，引用截图文件路径而非内嵌数据
      （设计决策 4）；截图失败为空串。
    :param llm_trace: 回溯报告专用；未调用 LLM 的节点为 ``None``。
    """

    node_type: str
    node_desc: str
    result: NodeResult
    timestamp: str
    action_call: ActionCall | None = None
    condition_result: bool | None = None
    page_url: str | None = None
    screenshot_path: str | None = None
    llm_trace: LeafTrace | None = None


@dataclass(frozen=True)
class NodeInfo:
    """当前执行节点信息（供 ``ExecState.current_node``，契约 §12.4）。"""

    node_type: str
    node_desc: str


@dataclass
class ExecState:
    """可查询执行状态（M8 spec §5.3、契约 §12.4）。

    :param run_id: 运行标识。
    :param current_node: 当前执行节点（``start_node`` 后、``record_node`` 前有效）。
    :param completed: 已完成节点的报告列表（即已记录的报告，决策 3 单数据源）。
    :param finished: 流程是否已结束（``finalize`` 置真）。
    :param total_nodes: 树中节点总数（执行前由 M2 解析产物可知）；未知时
      ``progress`` 保持 0.0，``finished`` 后恒为 1.0。
    """

    run_id: str
    current_node: NodeInfo | None = None
    completed: list[NodeReport] = field(default_factory=list)
    finished: bool = False
    total_nodes: int | None = None
    variables: list[dict] = field(default_factory=list)

    @property
    def progress(self) -> float:
        """执行进度 0.0~1.0：已完成节点数 / 总节点数（决策 3 派生，非存储字段）。"""
        if self.finished:
            return 1.0
        if not self.total_nodes:
            return 0.0
        return min(len(self.completed) / self.total_nodes, 1.0)


@dataclass(frozen=True)
class ExecReport:
    """执行情况报告（报告①，契约 §5.8.3）：每节点结果 + 截图，不含 LLM 推理。"""

    run_id: str
    path: str | None = None
    text: str = ""


@dataclass(frozen=True)
class TraceReport:
    """回溯报告（报告②，契约 §5.8.3）：执行详情 + LLM 推理，不含截图。"""

    run_id: str
    path: str | None = None
    text: str = ""


@dataclass(frozen=True)
class ReportBundle:
    """``finalize`` 返回值：由同一组节点报告派生的两份报告（决策 3）。"""

    exec_report: ExecReport
    trace_report: TraceReport
