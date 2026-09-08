"""语义图生成可分类错误（契约 §9.4 按错误源分流、spec 范围边界与失败语义）。

- ``SemanticGraphError``：基类。
- ``ProgramStageError``：程序侧失败（DOM 爬取失败、范围非法等），重试有意义。
- ``LlmStageError``：LLM 填充失败（重试无意义，应报告用户）。
- ``SemanticGraphBudgetExceeded``：token 预算超限（不静默截断）。
"""


class SemanticGraphError(Exception):
    """语义图生成错误基类。"""


class ProgramStageError(SemanticGraphError):
    """程序化阶段失败（DOM 爬取失败/范围非法等），重试有意义。"""


class LlmStageError(SemanticGraphError):
    """LLM 填充阶段失败，重试无意义。"""


class SemanticGraphBudgetExceeded(SemanticGraphError):
    """token 预算超限：可失败或提示降级，不静默返回截断的语义图。"""
