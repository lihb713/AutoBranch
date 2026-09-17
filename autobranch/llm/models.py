"""LLM 交互的数据结构（契约 M0 spec §5.1/§5.3/§5.4）。

``Message`` 为内部统一消息模型（设计决策 D3）：Chat Completions 与
Responses 两种协议都映射到同一消息序列，协议差异收敛在适配层。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ToolSpec:
    """可调用工具定义（随请求发送给模型，JSON Schema 格式）。

    :param name: 工具名。
    :param description: 工具说明。
    :param parameters: JSON Schema 格式的参数约束。
    """

    name: str
    description: str
    parameters: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    """模型发起的工具调用请求。

    :param id: 调用 id（回填结果时配对）。
    :param name: 工具名。
    :param arguments: 参数 JSON 字符串（合法时 `json.loads` 可解析）。
    """

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolResult:
    """工具执行结果，回填进会话。

    :param call_id: 对应 ``ToolCall.id``。
    :param content: 工具执行结果内容。
    """

    call_id: str
    content: str


@dataclass(frozen=True)
class LLMResponse:
    """一次请求的返回结果。

    :param text: 纯文本回复（无文本时为 ""）。
    :param tool_calls: 工具调用请求列表（无则为空列表）。
    """

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


@dataclass
class Message:
    """内部统一消息（协议无关）。

    :param role: ``system`` / ``user`` / ``assistant`` / ``tool``。
    :param content: 消息文本。
    :param tool_call_id: role=tool 时对应的调用 id。
    :param tool_calls: role=assistant 且包含工具调用请求时的列表。
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None
