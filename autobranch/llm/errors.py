"""LLM 调用可分类异常（契约 §9.4 按错误源分流）。

| 异常 | 错误源 | 重试语义 |
|---|---|---|
| ``LLMConnectionError`` | 网络/连接失败 | 程序侧，重试有意义 |
| ``LLMAuthError`` | 鉴权失败（401/403） | 配置问题，重试无意义 |
| ``LLMTimeoutError`` | 请求超时 | 程序侧，可重试 |
| ``LLMBudgetExceeded`` | token 预算超限 | 终止叶子 |
| ``LLMProtocolError`` | 响应无法解析 | 协议/模型问题 |
"""

from __future__ import annotations


class LLMError(Exception):
    """LLM 客户端错误基类。"""


class LLMConnectionError(LLMError):
    """网络层错误（连接失败、DNS 解析失败等）。"""


class LLMAuthError(LLMError):
    """鉴权失败（api_key 无效、无权限等）。"""


class LLMTimeoutError(LLMError):
    """请求超时。"""


class LLMBudgetExceeded(LLMError):
    """token 预算超限。"""


class LLMProtocolError(LLMError):
    """响应无法解析（协议格式错误、非法 JSON 等）。"""
