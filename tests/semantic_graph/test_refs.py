"""M4 任务 5.2：ref 映射表（引擎确定性分配 ref，``[N]`` ↔ 元素 id ↔ DOM 节点双向解析）。

ref 解析归引擎、不依赖 LLM 猜测（§7.8 策略 B）。
"""

from __future__ import annotations

from autobranch.semantic_graph.refs import build_ref_map
from snapshot_factory import login_snapshot

from autobranch.semantic_graph import run_programmatic


class TestRefAssignment:
    """引擎按阅读顺序确定性分配 ref（§7.8）。"""

    def test_refs_unique_and_ordered(self):
        result = run_programmatic(login_snapshot())
        refs = [element.ref for element in result.tree.elements]
        assert len(refs) == len(set(refs))
        assert refs == [f"[{i}]" for i in range(1, len(refs) + 1)]

    def test_ref_follows_reading_order(self):
        result = run_programmatic(login_snapshot())
        # 用户名 label 视觉上最先 → [1]
        user_label = next(e for e in result.tree.elements if e.dom_node_id == "n-user-label")
        assert user_label.ref == "[1]"
        username = next(e for e in result.tree.elements if e.dom_node_id == "n-username")
        assert username.ref == "[2]"

    def test_deterministic(self):
        first = run_programmatic(login_snapshot())
        second = run_programmatic(login_snapshot())
        assert [e.ref for e in first.tree.elements] == [e.ref for e in second.tree.elements]


class TestRefResolution:
    """§7.8：``[N]`` ↔ 元素 id ↔ DOM 节点 id 双向解析。"""

    def test_bidirectional_chain(self):
        result = run_programmatic(login_snapshot())
        ref_map = result.ref_map
        element = next(e for e in result.tree.elements if e.dom_node_id == "n-username")
        # [2] → 元素 id → DOM 节点 id
        assert ref_map.resolve("[2]") == element.id
        assert ref_map.dom_node_id("[2]") == element.dom_node_id
        # 反向
        assert ref_map.element_to_ref[element.id] == "[2]"

    def test_engine_not_llm_guessing(self):
        # ref 由引擎确定性映射，无 LLM 参与（§7.8 信任边界）
        result = run_programmatic(login_snapshot())
        for ref, element_id in result.ref_map.ref_to_element.items():
            element = next(e for e in result.tree.elements if e.id == element_id)
            assert element.ref == ref

    def test_build_ref_map_from_list(self):
        result = run_programmatic(login_snapshot())
        ref_map = build_ref_map(result.tree.elements)
        assert ref_map.resolve("[3]") is not None
