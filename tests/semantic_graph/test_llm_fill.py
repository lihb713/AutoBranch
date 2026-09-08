"""M4 任务 3.1~3.3：LLM 填充阶段（可注入填充器 + purpose + related-to 打分）。

mock 填充器注入后可跑通生成流水线；断言 purpose 写入正确、related-to 边
（含弱关联保留、score/reason/origin=visual）正确（§8.5/§8.6/§8.7）。
"""

from __future__ import annotations

import pytest
from snapshot_factory import SnapshotBuilder, login_snapshot

from webops.semantic_graph import MockFiller, generate_semantic_graph, run_programmatic
from webops.semantic_graph.errors import LlmStageError


def _element_by_dom(graph, node_id):
    return next(e for e in graph.elements if e.dom_node_id == node_id)


class TestFillerInterface:
    """任务 3.1：可注入填充器接口。"""

    def test_mock_filler_fills_purpose(self):
        filler = MockFiller(purposes={"n-username": "用户名输入框"})
        elements = run_programmatic(login_snapshot()).tree.elements
        result = filler.fill_purpose(elements, [])
        assert result.element_purposes  # 每个元素都有 purpose

    def test_mock_filler_defaults_to_role(self):
        filler = MockFiller()
        elements = run_programmatic(login_snapshot()).tree.elements
        result = filler.fill_purpose(elements, [])
        for element in elements:
            assert result.element_purposes[element.id] == element.role


class TestPipelineWithMockFiller:
    """任务 3.2：purpose 写入（mock 返回固定 purpose → 断言写入正确）。"""

    def test_purpose_written_into_elements(self):
        filler = MockFiller(
            purposes={
                "n-username": "用户名输入框",
                "n-password": "密码输入框",
                "n-login": "登录按钮",
            },
            region_labels={"F1": "登录区"},
        )
        graph = generate_semantic_graph(login_snapshot(), filler=filler)
        username = _element_by_dom(graph, "n-username")
        password = _element_by_dom(graph, "n-password")
        login_btn = _element_by_dom(graph, "n-login")
        assert username.purpose == "用户名输入框"
        assert password.purpose == "密码输入框"
        assert login_btn.purpose == "登录按钮"
        form = next(r for r in graph.regions if r.id == "F1")
        assert form.label == "登录区"

    def test_every_element_has_purpose(self):
        graph = generate_semantic_graph(login_snapshot(), filler=MockFiller())
        assert all(element.purpose for element in graph.elements)


class TestRelatedScoring:
    """任务 3.3：related-to 打分填充（弱关联保留、score/reason/origin=visual）。"""

    def test_related_edges_written(self):
        filler = MockFiller(
            purposes={"n-user-label": "用户名", "n-username": "用户名输入框"},
            related=[
                {
                    "from_id": "n-user-label",
                    "to_id": "n-username",
                    "score": 0.9,
                    "reason": "这是用户名的标签，视觉紧邻左侧",
                    "confidence": "explicit",
                },
                {
                    "from_id": "n-user-label",
                    "to_id": "n-password",
                    "score": 0.2,
                    "reason": "相距较远，且密码框已被占用",
                    "confidence": "inferred",
                },
            ],
        )
        graph = generate_semantic_graph(login_snapshot(), filler=filler)
        related = [edge for edge in graph.edges if edge.type == "related-to"]
        assert len(related) == 2
        strong = next(e for e in related if e.to_id == _element_by_dom(graph, "n-username").id)
        assert strong.from_id == _element_by_dom(graph, "n-user-label").id
        assert strong.score == 0.9
        assert strong.reason == "这是用户名的标签，视觉紧邻左侧"
        assert strong.origin == "visual"
        assert strong.confidence == "explicit"
        assert strong.detail == "左侧邻近"  # 几何推断依据
        weak = next(e for e in related if e.to_id == _element_by_dom(graph, "n-password").id)
        assert weak.score == 0.2  # 弱关联也保留（§7.5.5）

    def test_related_score_must_be_within_candidates(self):
        # LLM 对非候选对打分 → 边被丢弃（候选预筛约束，§8.5）
        b = SnapshotBuilder()
        nodes = [
            b.node("span", text=f"文本{i}", node_id=f"n-{i}", x=float(i * 20), y=0.0, w=10, h=10)
            for i in range(12)
        ]
        snapshot = b.snapshot(body_children=nodes)
        result = run_programmatic(snapshot)
        span0 = next(e for e in result.tree.elements if e.dom_node_id == "n-0")
        span11 = next(e for e in result.tree.elements if e.dom_node_id == "n-11")
        pairs = {(pair.from_id, pair.to_id) for pair in result.related_candidates}
        assert (span11.id, span0.id) not in pairs  # 超出最近 8 候选
        filler = MockFiller(
            related=[
                {"from_id": "n-11", "to_id": "n-0", "score": 0.9, "reason": "不应出现"}
            ]
        )
        graph = generate_semantic_graph(snapshot, filler=filler)
        assert not any(edge.type == "related-to" for edge in graph.edges)


class TestFailureSemantics:
    """填充阶段失败分类（§9.4、spec 失败可区分）。"""

    def test_filler_required(self):
        with pytest.raises(LlmStageError):
            generate_semantic_graph(login_snapshot(), filler=None)

    def test_filler_exception_wrapped_as_llm_stage_error(self):
        class BrokenFiller:
            def fill_purpose(self, elements, regions):
                raise RuntimeError("模型不可用")

            def score_related_to(self, candidates):
                return []

        with pytest.raises(LlmStageError):
            generate_semantic_graph(login_snapshot(), filler=BrokenFiller())
