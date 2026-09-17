"""M4 任务 6.2：集成冒烟（可选，真实 M0 LLM，``pytest -m smoke``）。

默认跳过；设置环境变量 ``AUTOBRANCH_TEST_LLM=1`` 且提供 ``AUTOBRANCH_LLM_BASE_URL`` /
``AUTOBRANCH_LLM_API_KEY`` / ``AUTOBRANCH_LLM_MODEL`` 时运行，人工检查 purpose/related-to
合理性（§8.5 真实 LLM 填充）。
"""

from __future__ import annotations

import os

import pytest

from autobranch.llm import LLMConfig, LLMSession
from autobranch.semantic_graph import LLMSessionFiller, semantic_graph, serialize

pytestmark = pytest.mark.smoke

_ENABLED = os.environ.get("AUTOBRANCH_TEST_LLM") == "1"


@pytest.mark.skipif(not _ENABLED, reason="真实 LLM 冒烟：需 AUTOBRANCH_TEST_LLM=1 与环境配置")
def test_real_llm_fill(sg_driver, sg_http_server, sg_open_page):
    base_url = os.environ.get("AUTOBRANCH_LLM_BASE_URL", "https://opencode.ai/zen/go/v1")
    api_key = os.environ["AUTOBRANCH_LLM_API_KEY"]
    model = os.environ.get("AUTOBRANCH_LLM_MODEL", "deepseek-v4-flash")

    page_ref = sg_open_page(f"{sg_http_server}/sg_login.html")
    session = LLMSession(
        LLMConfig(base_url=base_url, api_key=api_key, model=model),
        system_prompt="你是 AutoBranch 页面语义分析器，输出合法 JSON。",
    )
    # 先用程序化阶段获取 ref_map（填充器需要引擎分配的 ref）
    from autobranch.browser import DomProbe
    from autobranch.semantic_graph import run_programmatic

    snapshot = DomProbe(sg_driver).crawl(page_ref)
    programmatic = run_programmatic(snapshot)
    filler = LLMSessionFiller(session, programmatic.ref_map)

    graph = semantic_graph(
        page_ref,
        probe=DomProbe(sg_driver),
        filler=filler,
        budget_limit=20_000,
    )
    assert all(element.purpose for element in graph.elements)
    related = [edge for edge in graph.edges if edge.type == "related-to"]
    assert related, "真实 LLM 应产出 related-to 打分（供人工检查合理性）"
    print(serialize(graph))
