"""M7 任务 5.1~5.4：可查询执行状态（进度/当前节点/已完成报告/结束标记，§12.4）。"""

from __future__ import annotations

from orchestrator_helpers import (
    action,
    leaf_success,
    make_engine,
    seq,
)

from webops.parser.models import BehaviorTree


def _tree() -> BehaviorTree:
    return BehaviorTree(
        name="主流程",
        root=seq(action("a"), action("b"), action("c")),
    )


class TestExecStateStructure:
    """任务 5.1：ExecState（run_id/progress/current_node/completed/finished）挂入引擎。"""

    def test_empty_before_run(self) -> None:
        engine = make_engine()
        state = engine.get_exec_state()
        assert state.run_id == ""
        assert state.current_node is None
        assert state.completed == []
        assert state.finished is False

    def test_filled_after_run(self, config) -> None:
        engine = make_engine()
        engine.run(_tree(), config)
        state = engine.get_exec_state()
        assert state.run_id
        assert state.finished is True
        assert len(state.completed) == 4  # 3 叶子 + 1 Sequence
        assert state.progress == 1.0


class TestExecStateUpdates:
    """任务 5.2：进入写 current_node、退出追加 completed、progress 单调推进。"""

    def test_progress_monotonic_and_current_node(self, config) -> None:
        snapshots = []
        engine = make_engine()

        def probe(node, timeout):
            snapshots.append(engine.get_exec_state())
            return leaf_success(node.description)

        engine._leaf_executor = probe
        result = engine.run(_tree(), config)
        assert result.status == "success"
        progresses = [s.progress for s in snapshots]
        assert progresses == sorted(progresses)  # 单调非递减
        assert progresses[0] == 0.0  # 首个叶子执行前无已完成节点
        # 当前执行节点实时推进
        assert [s.current_node.node_desc for s in snapshots] == ["a", "b", "c"]
        # 进度按已完成节点数 / 总节点数推进（4 个节点）
        assert progresses == [0.0, 1 / 4, 2 / 4]

    def test_completed_accumulates_reports(self, config) -> None:
        engine = make_engine()
        engine.run(_tree(), config)
        state = engine.get_exec_state()
        descs = [r.node_desc for r in state.completed]
        # 叶子报告按执行顺序累积（后序：叶子在前，Sequence 在后）
        assert descs[:3] == ["a", "b", "c"]
        assert descs[-1] == "Sequence"

    def test_current_node_cleared_after_record(self, config) -> None:
        engine = make_engine()
        engine.run(_tree(), config)
        assert engine.get_exec_state().current_node is None  # 全部结束后清空


class TestExecStateSnapshot:
    """任务 5.3：get_exec_state 返回不可变快照（读侧安全，修改不影响内部）。"""

    def test_snapshot_is_copy(self, config) -> None:
        engine = make_engine()
        engine.run(_tree(), config)
        s1 = engine.get_exec_state()
        s2 = engine.get_exec_state()
        assert len(s1.completed) == len(s2.completed)
        s1.completed.append(s1.completed[0])
        assert len(s1.completed) == len(s2.completed) + 1
        assert len(engine.get_exec_state().completed) == len(s2.completed)

    def test_repeated_queries_consistent(self, config) -> None:
        engine = make_engine()
        engine.run(_tree(), config)
        a = engine.get_exec_state()
        b = engine.get_exec_state()
        assert a.progress == b.progress
        assert [r.node_desc for r in a.completed] == [r.node_desc for r in b.completed]


class TestExecStateFinished:
    """任务 5.4：运行结束后 finished 置位且 completed 含全部节点报告。"""

    def test_finished_and_full_completed(self, config) -> None:
        engine = make_engine()
        result = engine.run(_tree(), config)
        assert result.status == "success"
        state = engine.get_exec_state()
        assert state.finished is True
        assert state.progress == 1.0
        # 全部节点报告（3 叶子 + Sequence）
        assert len(state.completed) == 4
        assert all(r.result == "success" for r in state.completed)
