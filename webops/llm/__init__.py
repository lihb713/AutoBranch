"""WebOps LLM 客户端（M0）。

提供统一的 OpenAI 兼容 LLM 调用能力：配置管理、多轮工具调用会话、
上下文与 token 预算管理、可分类的错误语义。被 M6 叶子 agent 与
M4 语义图生成复用。无依赖、可独立测试。

对外公开的接口：
- ``LLMConfig`` / ``ToolSpec`` / ``ToolCall`` / ``LLMResponse`` / ``ToolResult``
- ``LLMSession``（agent 式会话）
- 可分类异常：``LLMConnectionError`` / ``LLMAuthError`` / ``LLMTimeoutError`` /
  ``LLMBudgetExceeded``
"""

from webops.llm.config import LLMConfig
from webops.llm.errors import (
    LLMAuthError,
    LLMBudgetExceeded,
    LLMConnectionError,
    LLMError,
    LLMProtocolError,
    LLMTimeoutError,
)
from webops.llm.models import LLMResponse, ToolCall, ToolResult, ToolSpec
from webops.llm.session import LLMSession

__all__ = [
    "LLMConfig",
    "LLMError",
    "LLMConnectionError",
    "LLMAuthError",
    "LLMTimeoutError",
    "LLMBudgetExceeded",
    "LLMProtocolError",
    "ToolSpec",
    "ToolCall",
    "ToolResult",
    "LLMResponse",
    "LLMSession",
]
