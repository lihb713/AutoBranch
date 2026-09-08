"""M8 任务 1.2 / 4.1 / 4.2：记录接口与执行状态维护/查询。"""

from __future__ import annotations

from reporting.factories import make_action_report, make_composite_report, make_condition_report

from webops.reporting import Reporter


class TestRecordNode:
    """任务 1.2：record_node 累积节点报告，顺序保持。"""

    def test_record_node_appends_in_order(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path))
        first = make_action_report(node_desc="第一步")
        second = make_condition_report(node_desc="第二步")
        third = make_composite_report(node_desc="第三步")
        reporter.record_node(first)
        reporter.record_node(second)
        reporter.record_node(third)
        completed = reporter.exec_state().completed
        assert [r.node_desc for r in completed] == ["第一步", "第二步", "第三步"]
        assert completed[0] is first

    def test_record_empty_reporter(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path))
        assert reporter.exec_state().completed == []
        assert reporter.exec_state().progress == 0.0


class TestExecStateMaintenance:
    """任务 4.1：节点完成时 completed 累积、progress 推进、current_node 更新、结束置 finished。"""

    def test_start_node_updates_current_node(self, tmp_path, node_info):
        reporter = Reporter("run-1", str(tmp_path))
        assert reporter.exec_state().current_node is None
        reporter.start_node(node_info)
        assert reporter.exec_state().current_node == node_info
        assert reporter.exec_state().current_node.node_desc == "点击登录"

    def test_record_node_clears_current_node(self, tmp_path, node_info):
        reporter = Reporter("run-1", str(tmp_path))
        reporter.start_node(node_info)
        reporter.record_node(make_action_report())
        assert reporter.exec_state().current_node is None

    def test_progress_advances_node_by_node(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path), total_nodes=4)
        assert reporter.exec_state().progress == 0.0
        reporter.record_node(make_action_report())
        assert reporter.exec_state().progress == 0.25
        reporter.record_node(make_condition_report())
        assert reporter.exec_state().progress == 0.5
        reporter.record_node(make_action_report())
        reporter.record_node(make_composite_report())
        assert reporter.exec_state().progress == 1.0
        assert len(reporter.exec_state().completed) == 4

    def test_finalize_marks_finished(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path), total_nodes=2)
        assert reporter.exec_state().finished is False
        reporter.record_node(make_action_report())
        reporter.record_node(make_condition_report())
        reporter.finalize()
        state = reporter.exec_state()
        assert state.finished is True
        assert state.progress == 1.0
        assert len(state.completed) == 2


class TestExecStateQuery:
    """任务 4.2：查询返回当前进度/当前节点/已完成报告，查询不改变执行状态。"""

    def test_query_returns_snapshot(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path), total_nodes=3)
        first = make_action_report()
        reporter.record_node(first)
        state = reporter.exec_state()
        assert state.progress == 1 / 3
        assert len(state.completed) == 1

        state.completed.append(make_condition_report())
        assert len(state.completed) == 2
        assert len(reporter.exec_state().completed) == 1

    def test_repeated_queries_consistent(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path), total_nodes=2)
        reporter.record_node(make_action_report())
        snapshot_a = reporter.exec_state()
        snapshot_b = reporter.exec_state()
        assert snapshot_a.progress == snapshot_b.progress == 0.5
        names_a = [r.node_desc for r in snapshot_a.completed]
        names_b = [r.node_desc for r in snapshot_b.completed]
        assert names_a == names_b
        assert len(reporter.exec_state().completed) == 1
