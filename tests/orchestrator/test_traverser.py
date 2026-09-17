"""M7 任务 1.3：基础节点统一 tick 契约（SUCCESS/FAILURE，阻塞式无 RUNNING）。"""

from __future__ import annotations

from orchestrator_helpers import (
    action,
    cond,
    leaf_failure,
    leaf_success,
    make_run_context,
)

from autobranch.orchestrator import FAILURE, SUCCESS
from autobranch.orchestrator.traverser import Traverser


class TestActionTick:
    """任务 1.3：Action 节点 mock 返回成功/失败时 tick 返回对应状态。"""

    def test_action_success(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["动作A"] = leaf_success("动作A")
        status = Traverser(ctx).tick(action("动作A"))
        assert status == SUCCESS
        assert len(ctx.leaf_executor.calls) == 1

    def test_action_failure(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["动作B"] = leaf_failure("动作B")
        status = Traverser(ctx).tick(action("动作B"))
        assert status == FAILURE
        assert ctx.failure_reason is not None
        assert "动作B" in ctx.failure_reason

    def test_condition_tick(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["条件C"] = leaf_success("条件C")
        assert Traverser(ctx).tick(cond("条件C")) == SUCCESS

    def test_tick_blocking_single_execution(self, config) -> None:
        """阻塞式：一次 tick 只触发一次叶子执行，前一个结束才执行下一个。"""
        ctx = make_run_context(config)
        traverser = Traverser(ctx)
        assert traverser.tick(action("动作C")) == SUCCESS
        assert traverser.tick(cond("条件C")) == SUCCESS
        assert len(ctx.leaf_executor.calls) == 2
        # 同一时刻至多一个叶子在执行：calls 是顺序追加的
        assert [n.description for n, _ in ctx.leaf_executor.calls] == ["动作C", "条件C"]

    def test_report_recorded_for_leaf(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["动作D"] = leaf_success("动作D")
        Traverser(ctx).tick(action("动作D"))
        reports = ctx.reporter.exec_state().completed
        assert len(reports) == 1
        assert reports[0].node_type == "Action"
        assert reports[0].node_desc == "动作D"
        assert reports[0].result == "success"
