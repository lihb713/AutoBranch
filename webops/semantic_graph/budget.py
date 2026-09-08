"""token 预算超限检测（契约 §9.5、spec §8.8 ⑤、design D6）。

基于 LOD + 范围 + 序列化估算：序列化文本 token 估算（复用 M0 ``estimate_tokens``）
+ LLM 填充阶段的固定提示词开销。超限时抛 ``SemanticGraphBudgetExceeded``，
不静默返回截断的语义图。
"""

from __future__ import annotations

from webops.llm.token import estimate_tokens
from webops.semantic_graph.errors import SemanticGraphBudgetExceeded
from webops.semantic_graph.models import SemanticGraph
from webops.semantic_graph.serialize import serialize

# LLM 填充阶段提示词/输出固定开销（粗估，保守）
LLM_PROMPT_OVERHEAD = 400


def estimate_graph_tokens(graph: SemanticGraph) -> int:
    """估算一次语义图的 token 消耗（序列化文本 + LLM 填充开销）。"""
    return estimate_tokens(serialize(graph)) + LLM_PROMPT_OVERHEAD


def check_budget(graph: SemanticGraph, budget_limit: int) -> None:
    """校验预算；超限抛 :class:`SemanticGraphBudgetExceeded`（可降级，不截断）。"""
    estimate = estimate_graph_tokens(graph)
    if estimate > budget_limit:
        raise SemanticGraphBudgetExceeded(
            f"语义图 token 预算超限: 估算 {estimate} > 上限 {budget_limit}"
            "（可降低 LOD 或缩小范围后重试）"
        )
