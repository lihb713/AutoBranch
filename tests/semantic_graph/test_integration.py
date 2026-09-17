"""M4 任务 6.1：集成测试（真实浏览器 + mock LLM，``pytest -m integration``）。

从真实页面（tests/fixtures/sg_login.html / sg_orders.html）经 M1 DOM 爬取 +
M4 两阶段流水线生成语义图，断言对象模型与序列化文本符合契约（§7/§8）。
"""

from __future__ import annotations

import pytest
from autobranch.semantic_graph.errors import LlmStageError
from autobranch.semantic_graph.llm_fill import RelatedScore

from autobranch.browser import DomProbe, ElementRef
from autobranch.semantic_graph import MockFiller, semantic_graph, serialize

pytestmark = pytest.mark.integration


class FirstPairFiller(MockFiller):
    """给几何候选首对固定打分的 mock 填充器（无需预知元素 id）。"""

    def score_related_to(self, candidates):
        if not candidates:
            return []
        first = candidates[0]
        return [
            RelatedScore(
                from_id=first.from_id,
                to_id=first.to_id,
                score=0.95,
                reason="集成测试固定打分",
                confidence="explicit",
            )
        ]


class TestIntegrationLogin:
    """真实页面生成语义图：对象模型 + 序列化文本符合契约。"""

    def test_login_graph_structure(self, sg_driver, sg_http_server, sg_open_page):
        page_ref = sg_open_page(f"{sg_http_server}/sg_login.html")
        graph = semantic_graph(
            page_ref,
            probe=DomProbe(sg_driver),
            filler=FirstPairFiller(),
        )
        assert graph.page.url.endswith("/sg_login.html")
        assert graph.page.title == "登录页"
        region_types = {region.region_type for region in graph.regions}
        assert "form" in region_types
        assert "nav" in region_types
        assert all(element.purpose for element in graph.elements)
        assert all(element.ref for element in graph.elements)

    def test_login_serialized_text(self, sg_driver, sg_http_server, sg_open_page):
        page_ref = sg_open_page(f"{sg_http_server}/sg_login.html")
        graph = semantic_graph(
            page_ref,
            probe=DomProbe(sg_driver),
            filler=FirstPairFiller(),
        )
        text = serialize(graph)
        assert text.startswith("PAGE: 登录页  URL=")
        assert "REGION FORM F1" in text
        assert "REGION NAV N1" in text
        assert "FIELD [" in text
        assert "ACTOR [" in text
        assert "LINK [" in text

    def test_every_call_reflects_input_change(
        self, sg_driver, sg_http_server, sg_open_page, sg_page_handle
    ):
        page_ref = sg_open_page(f"{sg_http_server}/sg_login.html")
        probe = DomProbe(sg_driver)
        filler = FirstPairFiller()

        def username_value():
            graph = semantic_graph(page_ref, probe=probe, filler=filler)
            # 视觉最上方的 textbox 即用户名输入框（密码框在下方）
            textboxes = [element for element in graph.elements if element.role == "textbox"]
            username = min(textboxes, key=lambda element: (element.bounds.y, element.bounds.x))
            return username.state.value

        assert username_value() == ""
        handle = sg_page_handle(page_ref)
        assert handle.type(ElementRef("#username"), "admin").ok
        assert username_value() == "admin"  # 无缓存，反映最新值（§9.5）

    def test_scope_region(self, sg_driver, sg_http_server, sg_open_page):
        page_ref = sg_open_page(f"{sg_http_server}/sg_login.html")
        graph = semantic_graph(
            page_ref,
            scope="N1",
            probe=DomProbe(sg_driver),
            filler=FirstPairFiller(),
        )
        assert [region.id for region in graph.regions] == ["N1"]
        assert all(element.role == "link" for element in graph.elements)

    def test_related_edges_written(self, sg_driver, sg_http_server, sg_open_page):
        page_ref = sg_open_page(f"{sg_http_server}/sg_login.html")
        graph = semantic_graph(
            page_ref,
            probe=DomProbe(sg_driver),
            filler=FirstPairFiller(),
        )
        related = [edge for edge in graph.edges if edge.type == "related-to"]
        assert related
        assert all(edge.origin == "visual" for edge in related)
        assert related[0].score == 0.95


class TestIntegrationOrders:
    """真实订单列表页：表格框架（value-of 边）与序列化。"""

    def test_table_framework(self, sg_driver, sg_http_server, sg_open_page):
        page_ref = sg_open_page(f"{sg_http_server}/sg_orders.html")
        graph = semantic_graph(
            page_ref,
            probe=DomProbe(sg_driver),
            filler=FirstPairFiller(),
        )
        assert any(region.region_type == "table" for region in graph.regions)
        assert any(region.region_type == "row" for region in graph.regions)
        value_of = [edge for edge in graph.edges if edge.type == "value-of"]
        assert value_of, "表格框架应派生 value-of 边"
        assert all(edge.origin == "structural" for edge in value_of)
        texts = {element.state.text for element in graph.elements}
        assert "¥98.00" in texts

    def test_orders_serialized(self, sg_driver, sg_http_server, sg_open_page):
        page_ref = sg_open_page(f"{sg_http_server}/sg_orders.html")
        graph = semantic_graph(
            page_ref,
            probe=DomProbe(sg_driver),
            filler=FirstPairFiller(),
        )
        text = serialize(graph)
        assert text.startswith("PAGE: 订单列表  URL=")
        assert "REGION TABLE T1" in text
        assert "REGION ROW R" in text
        assert 'CELL [' in text
        assert '="¥98.00"' in text  # 文本承载单元格携带金额文本


class TestIntegrationFailure:
    """真实浏览器下失败语义（§9.4：程序侧/LLM 侧可区分）。"""

    def test_program_stage_crawl_failure(self, sg_driver):
        from autobranch.browser import PageRef

        with pytest.raises(Exception) as exc_info:
            semantic_graph(
                PageRef("missing"),
                probe=DomProbe(sg_driver),
                filler=FirstPairFiller(),
            )
        from autobranch.semantic_graph.errors import ProgramStageError

        assert isinstance(exc_info.value, ProgramStageError)

    def test_llm_stage_failure(self, sg_driver, sg_http_server, sg_open_page):
        class BrokenFiller(FirstPairFiller):
            def fill_purpose(self, elements, regions):
                raise RuntimeError("模型不可用")

        page_ref = sg_open_page(f"{sg_http_server}/sg_login.html")
        with pytest.raises(LlmStageError):
            semantic_graph(
                page_ref,
                probe=DomProbe(sg_driver),
                filler=BrokenFiller(),
            )
