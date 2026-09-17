"""M4 任务 4.4：token 预算超限检测（LOD+范围+序列化估算，超限报告不静默截断）。"""

from __future__ import annotations

import pytest
from autobranch.semantic_graph.budget import estimate_graph_tokens
from autobranch.semantic_graph.errors import SemanticGraphBudgetExceeded
from snapshot_factory import login_snapshot

from autobranch.semantic_graph import MockFiller, generate_semantic_graph


class TestBudget:
    """§8.8 ⑤：预算超限可检测。"""

    def test_estimate_positive(self):
        graph = generate_semantic_graph(login_snapshot(), filler=MockFiller())
        assert estimate_graph_tokens(graph) > 0

    def test_budget_exceeded_raises(self):
        with pytest.raises(SemanticGraphBudgetExceeded):
            generate_semantic_graph(
                login_snapshot(), filler=MockFiller(), budget_limit=50
            )

    def test_budget_not_exceeded_passes(self):
        graph = generate_semantic_graph(
            login_snapshot(), filler=MockFiller(), budget_limit=1_000_000
        )
        assert graph.elements

    def test_no_silent_truncation(self):
        # 超限必须抛异常，不返回截断的语义图（design D6）
        with pytest.raises(SemanticGraphBudgetExceeded):
            generate_semantic_graph(
                login_snapshot(), filler=MockFiller(), budget_limit=1
            )

    def test_smaller_lod_reduces_budget(self):
        lod0 = generate_semantic_graph(login_snapshot(), lod=0, filler=MockFiller())
        lod3 = generate_semantic_graph(login_snapshot(), lod=3, filler=MockFiller())
        assert estimate_graph_tokens(lod0) < estimate_graph_tokens(lod3)
