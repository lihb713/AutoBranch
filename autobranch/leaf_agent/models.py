"""M6 叶子 agent 数据契约（M6 spec §5.1，对齐 M8 ``autobranch.reporting.models``）。

- ``ToolCallRecord``：单次引擎工具调用记录（函数名/参数/结果/是否成功/时间戳），
  支持序列化/反序列化。注意 M8 的 ``ToolCallRecord`` 不含时间戳字段，本模块
  使用带时间戳的扩展版本（超集），输出到 M8 ``LeafTrace`` 时经 ``to_m8``
  转回 M8 结构（时间戳不进 M8 追踪；若需在报告中展示时间戳，由上层跨模块
  对齐 M8 的 ``ToolCallRecord``）。
- ``LeafResult``：叶子执行结果契约（status/bool_value/error_source/trace）。
- ``LeafContext``：叶子执行上下文（LLM 配置 + M5 引擎函数 + 终止条件参数）。
- ``LeafTrace``：**复用 M8 定义**，其字段是 M6 spec §5.1 的超集（额外
  ``decision``），直接复用避免重复定义。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from autobranch.reporting.models import (
    LeafTrace,
)
from autobranch.reporting.models import (
    ToolCallRecord as ReportingToolCallRecord,
)

if TYPE_CHECKING:
    from autobranch.llm import LLMConfig, LLMSession, ToolSpec
    from autobranch.schema import SchemaSpace


@dataclass(frozen=True)
class ToolCallRecord:
    """单次引擎工具调用记录（M6 spec §5.1）。

    :param name: 引擎函数名。
    :param arguments: 调用参数（dict）。
    :param result: 工具结果文本（回传 LLM 的内容）。
    :param success: 该次调用是否成功。
    :param timestamp: 调用时间戳（epoch 秒）。
    """

    name: str
    arguments: dict[str, Any] | None = None
    result: str | None = None
    success: bool | None = None
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（参数中的非 JSON 值转字符串）。"""
        return {
            "name": self.name,
            "arguments": _jsonable(self.arguments),
            "result": self.result,
            "success": self.success,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolCallRecord:
        """反序列化（容忍缺失字段）。"""
        return cls(
            name=data.get("name", ""),
            arguments=data.get("arguments"),
            result=data.get("result"),
            success=data.get("success"),
            timestamp=data.get("timestamp", 0.0),
        )

    def to_m8(self) -> ReportingToolCallRecord:
        """转换为 M8 ``ToolCallRecord``（去掉时间戳，供 ``LeafTrace.calls``）。"""
        return ReportingToolCallRecord(
            name=self.name,
            arguments=self.arguments,
            result=self.result,
            success=self.success,
        )


@dataclass(frozen=True)
class LeafResult:
    """叶子执行结果契约（M6 spec §5.1、契约 §5.8.3）。

    :param status: 执行状态（success/failure）。
    :param bool_value: Condition 专有布尔值；Action 为 None。
    :param error_source: 失败来源（llm/program）；成功或 Condition 确定判断为 None。
    :param trace: 执行追踪数据（复用 M8 ``LeafTrace``）。
    """

    status: Literal["success", "failure"]
    bool_value: bool | None = None
    error_source: Literal["llm", "program"] | None = None
    trace: LeafTrace = field(default_factory=lambda: LeafTrace(llm_input={}))
    screenshots: tuple[str, ...] = ()


@dataclass(frozen=True)
class LeafContext:
    """叶子执行上下文（``execute_leaf`` 的 ctx 参数）。

    :param config: M0 LLM 配置（构建会话用）。
    :param engine: M5 引擎函数（``call(name, arguments)`` 分发入口）。
    :param space: M3 ``SchemaSpace``（get 变量替换用，叶子执行前程序读取
      blackboard；测试可注入）。
    :param session_factory: 会话工厂（测试注入 FakeTransport）；默认按
      ``config`` 构建真实会话（单次请求超时 ``session_timeout``）。
    :param tools: 初始工具集（默认能力概览 + ``use_capability``）。
    :param max_rounds: LLM 工具调用轮数上限（默认 10，契约 §5.7.2.1 ①）。
    :param no_progress_rounds: 连续无进展判定轮数（默认 2，契约 §9.7 ②）。
    :param timeout: 单叶子墙钟超时秒数（默认 120；None 不检测）。
    :param session_timeout: 单次 LLM 请求超时秒数（默认会话工厂使用）。
    :param initial_graph_scope: 初始语义图范围（默认 full）。
    :param initial_graph_lod: 初始语义图 LOD（默认 2）。
    """

    config: LLMConfig
    registry: Any
    space: SchemaSpace | None = None
    session_factory: Callable[[LLMConfig, str], LLMSession] | None = None
    tools: list[ToolSpec] | None = None
    runtime: Any = None
    max_rounds: int = 10
    no_progress_rounds: int = 2
    timeout: float | None = 240.0
    session_timeout: float = 60.0
    initial_graph_scope: str = "full"
    initial_graph_lod: int = 2


def _jsonable(value: Any) -> Any:
    """递归把不可 JSON 序列化的值转为字符串（供序列化）。"""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return str(value)


__all__ = ["ToolCallRecord", "LeafResult", "LeafContext"]
