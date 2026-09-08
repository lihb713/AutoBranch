"""M4 任务 4.1/4.2：统一入口 ``semantic_graph`` 与每次完整生成（无缓存）。

- 4.1：每次调用完整执行两阶段且无缓存，input 值变化反映到下次输出。
- 4.2：范围参数（全页/指定区域 id）过滤输出。
"""

from __future__ import annotations

import pytest
from snapshot_factory import SnapshotBuilder, login_snapshot

from webops.browser.models import PageRef
from webops.semantic_graph import MockFiller, semantic_graph
from webops.semantic_graph.errors import LlmStageError, ProgramStageError


class StubProbe:
    """可注入的 DOM 爬取桩（模拟 M1 DomProbe，返回预设快照）。"""

    def __init__(self, snapshots):
        self._snapshots = list(snapshots)
        self.calls = 0

    def crawl(self, page_ref, lod=None):
        self.calls += 1
        if not self._snapshots:
            raise RuntimeError("预设快照耗尽")
        return self._snapshots.pop(0)


def _by_dom(graph, node_id):
    return next(element for element in graph.elements if element.dom_node_id == node_id)


class TestEveryCallFullGeneration:
    """任务 4.1：每次调用完整生成、无缓存、反映最新输入值（§9.5）。"""

    def test_input_change_reflected_next_call(self):
        b = SnapshotBuilder()
        snapshot_v1 = b.snapshot(
            body_children=[
                b.node("input", value="初始值", node_id="n-v", dom_id="v", x=10, y=10, w=80, h=20)
            ],
            title="动态页",
        )
        snapshot_v2 = b.snapshot(
            body_children=[
                b.node("input", value="新值", node_id="n-v", dom_id="v", x=10, y=10, w=80, h=20)
            ],
            title="动态页",
        )
        probe = StubProbe([snapshot_v1, snapshot_v2])
        filler = MockFiller(purposes={"n-v": "动态输入框"})
        ref = PageRef("P1")

        first = semantic_graph(ref, probe=probe, filler=filler)
        assert _by_dom(first, "n-v").state.value == "初始值"

        second = semantic_graph(ref, probe=probe, filler=filler)
        assert probe.calls == 2  # 每次都重新爬取（程序化阶段重跑）
        assert _by_dom(second, "n-v").state.value == "新值"

    def test_each_call_runs_filler(self):
        class CountingFiller(MockFiller):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def fill_purpose(self, elements, regions):
                self.calls += 1
                return super().fill_purpose(elements, regions)

            def score_related_to(self, candidates):
                self.calls += 1
                return super().score_related_to(candidates)

        filler = CountingFiller()
        probe = StubProbe([login_snapshot(), login_snapshot()])
        ref = PageRef("P1")
        semantic_graph(ref, probe=probe, filler=filler)
        semantic_graph(ref, probe=probe, filler=filler)
        assert filler.calls == 4  # 两次调用 ×（purpose + related）

    def test_injection_required(self):
        ref = PageRef("P1")
        with pytest.raises(ProgramStageError):
            semantic_graph(ref, probe=None, filler=MockFiller())
        with pytest.raises(LlmStageError):
            semantic_graph(ref, probe=StubProbe([login_snapshot()]), filler=None)


class TestScopeFilter:
    """任务 4.2：范围参数控制广度（§8.8 范围）。"""

    def test_scope_full_includes_all(self):
        probe = StubProbe([login_snapshot()])
        graph = semantic_graph(PageRef("P1"), scope="full", probe=probe, filler=MockFiller())
        assert {region.id for region in graph.regions} == {"F1", "N1"}
        assert len(graph.elements) == 11

    def test_scope_region_only(self):
        probe = StubProbe([login_snapshot()])
        graph = semantic_graph(PageRef("P1"), scope="F1", probe=probe, filler=MockFiller())
        assert [region.id for region in graph.regions] == ["F1"]
        assert all(element.dom_node_id.startswith("n-user") or element.dom_node_id in
                   ("n-username", "n-password", "n-remember", "n-login", "n-forgot",
                    "n-pass-label", "n-remember-label")
                   for element in graph.elements)
        assert not any(element.dom_node_id in ("n-orders", "n-report", "n-greeting")
                       for element in graph.elements)

    def test_scope_by_ref(self):
        probe = StubProbe([login_snapshot()])
        graph = semantic_graph(PageRef("P1"), scope="N1", probe=probe, filler=MockFiller())
        assert [region.id for region in graph.regions] == ["N1"]
        assert {element.dom_node_id for element in graph.elements} == {
            "n-orders",
            "n-report",
        }

    def test_unknown_scope_raises_program_error(self):
        probe = StubProbe([login_snapshot()])
        with pytest.raises(ProgramStageError):
            semantic_graph(PageRef("P1"), scope="X99", probe=probe, filler=MockFiller())


class TestLodParam:
    """接口接受 LOD 级别 0~3 与 LODSpec。"""

    def test_lod_level_accepted(self):
        probe = StubProbe([login_snapshot()])
        graph = semantic_graph(PageRef("P1"), lod=0, probe=probe, filler=MockFiller())
        assert graph.elements  # LOD-0 也产出候选

    def test_invalid_lod_rejected(self):
        probe = StubProbe([login_snapshot()])
        with pytest.raises(ValueError):
            semantic_graph(PageRef("P1"), lod=9, probe=probe, filler=MockFiller())
