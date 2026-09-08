"""token 统计与预算管理（设计决策 D5）。

优先取响应 ``usage`` 精确累加；端点未返回用量时，退化为按消息内容长度
做保守估算，并标注来源（estimated）。预算超限检测在本模块完成。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from webops.llm.errors import LLMBudgetExceeded


@dataclass(frozen=True)
class TokenAccount:
    """单次请求的 token 记录。

    :param tokens: 本次消耗的 token 数。
    :param source: ``usage``（端点返回）或 ``estimated``（保守估算）。
    """

    tokens: int
    source: str = "usage"


def account_from_usage(usage: dict | None) -> TokenAccount:
    """从响应 usage 提取 token 数；缺失时按 0 返回（由调用方决定是否估算）。

    兼容两种形态的 usage 字段：
    - Chat Completions: ``prompt_tokens`` / ``completion_tokens`` / ``total_tokens``
    - Responses: ``input_tokens`` / ``output_tokens`` / ``total_tokens``
    """
    if not isinstance(usage, dict):
        return TokenAccount(tokens=0, source="usage")
    total = usage.get("total_tokens")
    if isinstance(total, int):
        return TokenAccount(tokens=total, source="usage")
    parts = [
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
        usage.get("input_tokens"),
        usage.get("output_tokens"),
    ]
    int_parts = [p for p in parts if isinstance(p, int)]
    if int_parts:
        return TokenAccount(tokens=sum(int_parts), source="usage")
    return TokenAccount(tokens=0, source="usage")


def estimate_tokens(text: str) -> int:
    """保守估算 token 数（无 usage 时兜底）。

    按「非空白字符数 / 3 + 1」粗略估算，偏向保守（宁可高估避免预算形同虚设）。
    """
    meaningful = sum(1 for ch in text if not ch.isspace())
    return max(1, math.ceil(meaningful / 3))


class TokenBudget:
    """会话级 token 统计与预算检测。"""

    def __init__(self, budget_limit: int | None = None) -> None:
        self._budget_limit = budget_limit
        self._total = 0
        self._accounts: list[TokenAccount] = []

    def add(self, account: TokenAccount) -> None:
        self._total += account.tokens
        self._accounts.append(account)

    @property
    def total(self) -> int:
        return self._total

    @property
    def limit(self) -> int | None:
        return self._budget_limit

    def exceeds(self, limit: int) -> bool:
        return self._total > limit

    def check_and_raise(self) -> None:
        """累计 token 超过预算上限时抛 ``LLMBudgetExceeded``。"""
        if self._budget_limit is not None and self._total > self._budget_limit:
            raise LLMBudgetExceeded(
                f"LLM token 预算超限: 累计 {self._total} > 上限 {self._budget_limit}"
            )

    def estimated_flag(self) -> bool:
        """是否发生过估算（无 usage 的请求）。"""
        return any(a.source == "estimated" for a in self._accounts)
