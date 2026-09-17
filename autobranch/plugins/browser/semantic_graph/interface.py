"""语义图统一入口（契约 §8.8、spec §8.8/§9.5）。

``semantic_graph(page_ref, scope, lod)``：每次调用完整执行程序化阶段与
LLM 填充阶段，无缓存、无指纹、无失效机制（§9.5）。范围控制广度、LOD 控制
精细程度；token 预算超限可检测（§8.8 ⑤）。
"""

from __future__ import annotations

from autobranch.plugins.browser.driver.dom import DomProbe
from autobranch.plugins.browser.driver.errors import FatalBrowserError, PageRefError
from autobranch.plugins.browser.driver.models import LODSpec, PageRef
from autobranch.plugins.browser.semantic_graph.errors import LlmStageError, ProgramStageError
from autobranch.plugins.browser.semantic_graph.llm_fill import LlmFiller
from autobranch.plugins.browser.semantic_graph.models import SemanticGraph
from autobranch.plugins.browser.semantic_graph.pipeline import generate_semantic_graph


def semantic_graph(
    page_ref: PageRef,
    scope: str = "full",
    lod: int | LODSpec = 2,
    probe: DomProbe | None = None,
    filler: LlmFiller | None = None,
    budget_limit: int | None = None,
) -> SemanticGraph:
    """生成指定页面的语义图（每次完整生成，无缓存，§8.8/§9.5）。

    :param page_ref: 页面引用（M1，§5.10）。
    :param scope: ``full`` 全页或指定区域 id（如 ``F1``/``T1``，§8.8 范围）。
    :param lod: LOD 级别 0~3 或 ``LODSpec``（§9.5 四维组合）。
    :param probe: M1 ``DomProbe``（DOM 爬取）；由调用方（M5 引擎函数层）注入。
    :param filler: ``LlmFiller`` 实现（LLM 填充）；由调用方注入。
    :param budget_limit: token 预算上限（None 不检测）。
    :raises ProgramStageError: 程序侧失败（DOM 爬取失败/范围非法），可重试。
    :raises LlmStageError: LLM 填充失败，重试无意义。
    :raises SemanticGraphBudgetExceeded: token 预算超限。
    """
    if probe is None:
        raise ProgramStageError("semantic_graph 需要注入 DomProbe（M1 浏览器驱动）")
    if filler is None:
        raise LlmStageError("semantic_graph 需要注入 LlmFiller（LLM 填充器）")
    try:
        snapshot = probe.crawl(page_ref, LODSpec.from_level(3))
    except PageRefError as exc:
        raise ProgramStageError(f"DOM 爬取失败（页面引用无效）: {exc}") from exc
    except FatalBrowserError:
        raise
    return generate_semantic_graph(
        snapshot, scope=scope, lod=lod, filler=filler, budget_limit=budget_limit
    )
