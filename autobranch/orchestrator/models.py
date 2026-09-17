"""M7 编排器数据契约（M7 spec §5.1/§5.2、契约 §5.7.7/§5.9/§12.4）。

- ``NodeStatus`` / ``SUCCESS`` / ``FAILURE``：节点状态常量（阻塞式遍历，
  无 RUNNING 中间状态，契约 §5.7.7）。
- ``RunConfig``：一次运行的全局配置——全局超时、叶子上下文参数、浏览器配置、
  报告目录与 M0/M5 依赖注入（真实叶子执行需要，mock 叶子无需）。
- ``RunResult``：``Engine.run`` 返回值（状态 + 失败原因 + 两份报告，§5.1）。
- ``OrchestratorError``：编排器运行期错误基类（真实叶子缺依赖、帧路径不匹配、
  递归超深等）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from autobranch.schema.models import Value

if TYPE_CHECKING:
    from autobranch.browser.config import BrowserConfig
    from autobranch.llm import LLMConfig, LLMSession
    from autobranch.reporting.models import ExecReport, TraceReport

NodeStatus = Literal["success", "failure"]

#: 节点状态常量：成功。
SUCCESS: NodeStatus = "success"
#: 节点状态常量：失败（唯一两种状态之一，无 RUNNING）。
FAILURE: NodeStatus = "failure"


@dataclass(frozen=True)
class RunConfig:
    """运行配置（M7 spec §5.1/§5.4）。

    :param timeout: 全局叶子超时秒数（默认 120，None 表示不检测；注入根级
      schema 的 ``timeout`` 配置参数，作为继承链最终兜底，可被块级覆盖）。
    :param max_rounds: 叶子 LLM 工具调用轮数上限（传 M6，默认 10）。
    :param no_progress_rounds: 连续无进展判定轮数（传 M6，默认 2）。
    :param session_timeout: 单次 LLM 请求超时秒数（传 M6，默认 60）。
    :param initial_graph_scope: 初始语义图范围（传 M6，默认 full）。
    :param initial_graph_lod: 初始语义图 LOD（传 M6，默认 2）。
    :param report_dir: 报告持久化根目录（M8）。
    :param browser_config: M1 浏览器配置（None 用 M1 默认）。
    :param global_config: 注入根级 schema 的额外全局默认配置参数（§5.7.5）。
    :param llm_config: M0 LLM 配置（真实叶子执行需要；mock 叶子无需）。
    :param session_factory: 会话工厂（传 M6，测试注入假传输用）。
    """

    timeout: float | None = 120.0
    max_rounds: int = 10
    no_progress_rounds: int = 2
    session_timeout: float = 60.0
    initial_graph_scope: str = "full"
    initial_graph_lod: int = 2
    report_dir: str = "reports"
    browser_config: BrowserConfig | None = None
    global_config: dict[str, Value] = field(default_factory=dict)
    llm_config: LLMConfig | None = None
    session_factory: Callable[[LLMConfig, str], LLMSession] | None = None


@dataclass(frozen=True)
class RunResult:
    """引擎运行结果（M7 spec §5.1）。

    :param status: 最终状态（success/failure）。
    :param failure_reason: 失败原因（失败时非空，指向首个失败叶子/终止根因）。
    :param exec_report: 执行报告（报告①，M8 生成）；校验失败不启动遍历时为 None。
    :param trace_report: 回溯报告（报告②，M8 生成）；校验失败不启动遍历时为 None。
    """

    status: NodeStatus
    failure_reason: str | None = None
    exec_report: ExecReport | None = None
    trace_report: TraceReport | None = None


class OrchestratorError(Exception):
    """编排器运行期错误（真实叶子缺依赖、schema 帧路径不匹配、递归超深等）。"""


__all__ = [
    "NodeStatus",
    "SUCCESS",
    "FAILURE",
    "RunConfig",
    "RunResult",
    "OrchestratorError",
]
