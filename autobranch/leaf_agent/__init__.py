"""AutoBranch 叶子 agent 执行（M6）。

实现 Action / Condition 叶子节点的 agent 式执行（契约 §5.7.2）：将节点自然
语言描述 + 当前语义图提供给 LLM，由 LLM 自主调用 M5 引擎函数或判断条件真伪，
引擎只做兜底（终止条件 + 错误分类）。模块 spec 见 ``docs/specs/M6-leaf-agent.md``。

对外公开：
- ``execute_leaf(node, ctx) -> LeafResult``：叶子统一执行入口
- ``LeafContext`` / ``LeafResult`` / ``ToolCallRecord``：执行上下文与结果契约
- ``LeafTrace``：复用 M8 定义（``autobranch.reporting.models.LeafTrace``）
- 提示词：``PROMPT_VERSION`` / ``build_system_prompt`` / ``build_user_message``
"""

from autobranch.leaf_agent.executor import execute_leaf
from autobranch.leaf_agent.models import LeafContext, LeafResult, ToolCallRecord
from autobranch.leaf_agent.prompts import (
    PROMPT_VERSION,
    DecisionError,
    build_system_prompt,
    build_user_message,
)
from autobranch.reporting.models import LeafTrace

__all__ = [
    "execute_leaf",
    "LeafContext",
    "LeafResult",
    "ToolCallRecord",
    "LeafTrace",
    "PROMPT_VERSION",
    "build_system_prompt",
    "build_user_message",
    "DecisionError",
]
