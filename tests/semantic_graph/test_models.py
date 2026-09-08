"""M4 任务 1.1：语义图对象模型（dataclass 契约、RefMap、id/ref 唯一性校验）。

对齐契约 §7.5（Graph/Region/Element/Edge/Change）与 §7.8（ref 映射表）。
"""

from __future__ import annotations

from webops.browser.models import Bounds
from webops.semantic_graph import (
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


def make_graph() -> SemanticGraph:
    """构造一个合法语义图（登录表单场景）。"""
    ref_map = RefMap(
        ref_to_element={"[1]": "E1", "[2]": "E2", "[3]": "E3"},
        element_to_ref={"E1": "[1]", "E2": "[2]", "E3": "[3]"},
        element_to_dom={"E1": "N1", "E2": "N2", "E3": "N3"},
    )
    return SemanticGraph(
        page=PageInfo(url="https://example.com/login", title="登录页"),
        regions=[
            Region(id="F1", ref="[F1]", region_type="form", label="登录区", depth=0)
        ],
        elements=[
            Element(
                id="E1",
                ref="[1]",
                role="textbox",
                purpose="用户名输入框",
                state=ElementState(value="", text=""),
                dom_node_id="N1",
            ),
            Element(
                id="E2",
                ref="[2]",
                role="textbox",
                purpose="密码输入框",
                state=ElementState(value="", text=""),
                dom_node_id="N2",
            ),
            Element(
                id="E3",
                ref="[3]",
                role="button",
                purpose="登录按钮",
                state=ElementState(text="登录"),
                dom_node_id="N3",
            ),
        ],
        edges=[
            Edge(
                id="ED1",
                type="part-of",
                from_id="E1",
                to_id="F1",
                origin="structural",
            ),
            Edge(
                id="ED2",
                type="related-to",
                from_id="E1",
                to_id="E3",
                origin="visual",
                score=0.8,
                reason="标签-控件对",
            ),
        ],
        ref_map=ref_map,
    )


class TestObjectModel:
    """任务 1.1：对象模型字段契约（§7.5）。"""

    def test_graph_fields(self):
        graph = make_graph()
        assert graph.type == "semantic-graph"
        assert graph.version == "0.1"
        assert graph.page.url == "https://example.com/login"
        assert graph.page.title == "登录页"
        assert len(graph.regions) == 1
        assert len(graph.elements) == 3
        assert len(graph.edges) == 2
        assert graph.changes == []

    def test_element_fields(self):
        element = make_graph().elements[0]
        assert element.id == "E1"
        assert element.ref == "[1]"
        assert element.role == "textbox"
        assert element.purpose == "用户名输入框"
        assert element.state.value == ""
        assert element.bounds is None
        assert element.confidence == "explicit"

    def test_region_fields(self):
        region = make_graph().regions[0]
        assert region.id == "F1"
        assert region.ref == "[F1]"
        assert region.region_type == "form"
        assert region.label == "登录区"
        assert region.depth == 0

    def test_edge_fields(self):
        related = [e for e in make_graph().edges if e.type == "related-to"][0]
        assert related.origin == "visual"
        assert related.score == 0.8
        assert related.reason == "标签-控件对"

    def test_bounds_roundtrip(self):
        bounds = Bounds(x=10, y=20, w=30, h=40)
        element = Element(id="E1", ref="[1]", role="textbox", bounds=bounds)
        assert element.bounds.x == 10
        assert element.bounds.h == 40

    def test_change_optional(self):
        graph = make_graph()
        assert graph.changes == []
        graph.changes.append(Change(type="appeared", node_id="D1", summary="弹窗出现"))
        assert graph.changes[0].type == "appeared"

    def test_text_is_element_attribute(self):
        element = Element(id="E9", ref="[9]", role="cell", state=ElementState(text="¥98.00"))
        assert element.is_text_bearing is True
        assert element.state.text == "¥98.00"


class TestValidation:
    """任务 1.1：id/ref 唯一性校验（validate_graph）。"""

    def test_valid_graph_has_no_problems(self):
        assert validate_graph(make_graph()) == []

    def test_duplicate_element_id_detected(self):
        graph = make_graph()
        graph.elements[0].id = graph.elements[1].id
        assert any("id 不唯一" in problem for problem in validate_graph(graph))

    def test_duplicate_ref_detected(self):
        graph = make_graph()
        graph.elements[0].ref = graph.elements[1].ref
        assert any("ref 不唯一" in problem for problem in validate_graph(graph))

    def test_dangling_edge_endpoint_detected(self):
        graph = make_graph()
        graph.edges[1].from_id = "E999"
        assert any("from 端点不存在" in problem for problem in validate_graph(graph))

    def test_ref_not_in_mapping_detected(self):
        graph = make_graph()
        del graph.ref_map.ref_to_element[graph.elements[0].ref]
        assert any("不在 ref 映射表" in problem for problem in validate_graph(graph))


class TestRefMap:
    """任务 1.1/5.2：ref 映射表双向解析（§7.8）。"""

    def test_bidirectional_resolution(self):
        graph = make_graph()
        ref_map = graph.ref_map
        assert ref_map.resolve("[1]") == "E1"
        assert ref_map.element_to_ref["E1"] == "[1]"
        assert ref_map.dom_node_id("[1]") == "N1"

    def test_resolve_unknown_ref(self):
        ref_map = RefMap()
        assert ref_map.resolve("[99]") is None
        assert ref_map.dom_node_id("[99]") is None
