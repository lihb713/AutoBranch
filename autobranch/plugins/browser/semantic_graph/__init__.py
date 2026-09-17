"""AutoBranch 语义图生成（M4）。

把 M1 爬取的 DOM 快照经两阶段流水线（程序化 + LLM 填充）加工为语义图对象模型，
并提供 LOD 分级的 ``semantic_graph`` 统一接口与 LLM 可读的层次树序列化文本
（契约 §7/§8/§9.5，模块 spec docs/specs/M4-semantic-graph.md）。

对外公开的接口：
- ``semantic_graph``（统一入口，§8.8，每次完整生成无缓存）
- 对象模型：``SemanticGraph`` / ``Region`` / ``Element`` / ``Edge`` / ``Change`` / ``RefMap``
- 程序化阶段：``run_programmatic``（纯程序、零 LLM，可独立测试）
- LLM 填充器：``LlmFiller`` / ``MockFiller`` / ``LLMSessionFiller``
- 序列化：``serialize``（引擎对象模型 → LLM 层次树文本）
- LOD：复用 M1 ``LODSpec``（§9.5 四维），四维裁剪在 ``lod.py``
- 可分类错误：``ProgramStageError`` / ``LlmStageError`` / ``SemanticGraphBudgetExceeded``
"""

from autobranch.plugins.browser.semantic_graph.errors import (
    LlmStageError,
    ProgramStageError,
    SemanticGraphBudgetExceeded,
    SemanticGraphError,
)
from autobranch.plugins.browser.semantic_graph.interface import semantic_graph
from autobranch.plugins.browser.semantic_graph.llm_fill import (
    LlmFiller,
    LLMSessionFiller,
    MockFiller,
)
from autobranch.plugins.browser.semantic_graph.models import (
    Change,
    Edge,
    Element,
    ElementState,
    PageInfo,
    RefMap,
    Region,
    SemanticGraph,
    validate_graph,
)
from autobranch.plugins.browser.semantic_graph.pipeline import generate_semantic_graph
from autobranch.plugins.browser.semantic_graph.programmatic import (
    ProgrammaticResult,
    run_programmatic,
)
from autobranch.plugins.browser.semantic_graph.serialize import serialize

__all__ = [
    "semantic_graph",
    "generate_semantic_graph",
    "run_programmatic",
    "ProgrammaticResult",
    "LlmFiller",
    "MockFiller",
    "LLMSessionFiller",
    "SemanticGraph",
    "Region",
    "Element",
    "ElementState",
    "Edge",
    "Change",
    "PageInfo",
    "RefMap",
    "validate_graph",
    "serialize",
    "SemanticGraphError",
    "ProgramStageError",
    "LlmStageError",
    "SemanticGraphBudgetExceeded",
]
