"""M4 任务 2.5：related-to 几何候选预筛（bounds 邻近性，不直接成边）。

fixture 断言候选集正确（§8.7 候选输入、D3 程序化给候选、LLM 定语义）。
"""

from __future__ import annotations

from autobranch.semantic_graph.candidates import geometric_candidates
from snapshot_factory import login_snapshot

from autobranch.semantic_graph import run_programmatic


class TestGeometricCandidates:
    """§8.7：按 bounds 邻近性产出候选，带方位推断依据。"""

    def test_candidates_not_edges(self):
        result = run_programmatic(login_snapshot())
        assert result.related_candidates, "应有几何候选"
        assert not any(
            edge.type == "related-to" for edge in result.edges
        ), "程序化阶段不直接成 related-to 边"

    def test_label_to_input_candidate_present(self):
        result = run_programmatic(login_snapshot())
        by_node = {element.dom_node_id: element for element in result.tree.elements}
        label = by_node["n-user-label"]
        username = by_node["n-username"]
        pair = next(
            (
                p
                for p in result.related_candidates
                if p.from_id == label.id and p.to_id == username.id
            ),
            None,
        )
        assert pair is not None
        assert pair.detail == "左侧邻近"  # 用户名 span 在输入框左侧

    def test_password_label_candidate(self):
        result = run_programmatic(login_snapshot())
        by_node = {element.dom_node_id: element for element in result.tree.elements}
        label = by_node["n-pass-label"]
        password = by_node["n-password"]
        pair = next(
            (
                p
                for p in result.related_candidates
                if p.from_id == label.id and p.to_id == password.id
            ),
            None,
        )
        assert pair is not None
        assert pair.detail == "左侧邻近"

    def test_vertical_proximity_detail(self):
        result = run_programmatic(login_snapshot())
        by_node = {element.dom_node_id: element for element in result.tree.elements}
        greeting = by_node["n-greeting"]
        # 欢迎 span 与下方元素/上方的候选带上下方位
        vertical = [p for p in result.related_candidates if p.from_id == greeting.id]
        assert vertical
        assert all(p.detail.endswith("邻近") for p in vertical)

    def test_candidate_limited_per_target(self):
        result = run_programmatic(login_snapshot())
        from collections import Counter

        counts = Counter(p.to_id for p in result.related_candidates)
        assert max(counts.values()) <= 8  # MAX_PAIRS_PER_ELEMENT


class TestCandidateDeterminism:
    """候选生成确定性（同输入同输出）。"""

    def test_deterministic(self):
        first = run_programmatic(login_snapshot())
        second = run_programmatic(login_snapshot())
        first_pairs = [(p.from_id, p.to_id, p.detail) for p in first.related_candidates]
        second_pairs = [(p.from_id, p.to_id, p.detail) for p in second.related_candidates]
        assert first_pairs == second_pairs


class TestBareFunction:
    """geometric_candidates 单测（§8.7 预筛输入）。"""

    def test_elements_without_bounds_excluded(self):
        from autobranch.semantic_graph import Element, ElementState

        a = Element(id="E1", ref="[1]", role="span", state=ElementState(text="a"), bounds=None)
        b = Element(id="E2", ref="[2]", role="textbox", bounds=None)
        assert geometric_candidates([a, b]) == []
