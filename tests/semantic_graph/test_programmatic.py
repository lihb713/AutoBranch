"""M4 任务 2.6：程序化阶段整体独立验证（不依赖 LLM 与真实浏览器）。"""

from __future__ import annotations

from snapshot_factory import login_snapshot, orders_snapshot

from autobranch.semantic_graph import run_programmatic


class TestProgrammaticIndependence:
    """程序化阶段零 LLM、零浏览器可独立运行。"""

    def test_login_page_programmatic_output(self):
        result = run_programmatic(login_snapshot())
        assert result.tree.regions
        assert result.tree.elements
        assert result.edges
        assert result.ref_map.ref_to_element
        assert result.related_candidates

    def test_orders_page_programmatic_output(self):
        result = run_programmatic(orders_snapshot())
        assert any(edge.type == "value-of" for edge in result.edges)
        assert any(region.region_type == "table" for region in result.tree.regions)

    def test_ref_map_deterministic(self):
        first = run_programmatic(login_snapshot())
        second = run_programmatic(login_snapshot())
        assert first.ref_map.ref_to_element == second.ref_map.ref_to_element


class TestIndependenceSmoke:
    """模块独立性：子模块不 import autobranch.llm。"""

    def test_programmatic_modules_do_not_import_llm(self):
        import importlib

        for name in (
            "autobranch.semantic_graph.programmatic",
            "autobranch.semantic_graph.selection",
            "autobranch.semantic_graph.geometry",
            "autobranch.semantic_graph.values",
            "autobranch.semantic_graph.enrich",
            "autobranch.semantic_graph.candidates",
            "autobranch.semantic_graph.refs",
            "autobranch.semantic_graph.lod",
        ):
            module = importlib.import_module(name)
            assert "autobranch.llm" not in module.__dict__
