"""M7 任务 3.1~3.5：叶子触发、追踪记录、失败传播与全局超时。"""

from __future__ import annotations

from orchestrator_helpers import (
    BlockingLeaf,
    action,
    cond,
    leaf_condition,
    leaf_failure,
    leaf_success,
    make_run_context,
    seq,
)

from webops.orchestrator import FAILURE, SUCCESS
from webops.orchestrator.traverser import Traverser
from webops.reporting.models import LeafTrace


class TestLeafTrigger:
    """任务 3.1：Action/Condition 叶子触发与状态映射。"""

    def test_action_status_mapping(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["成功动作"] = leaf_success("成功动作")
        ctx.leaf_executor.results["失败动作"] = leaf_failure("失败动作")
        assert Traverser(ctx).tick(action("成功动作")) == SUCCESS
        assert Traverser(ctx).tick(action("失败动作")) == FAILURE

    def test_condition_bool_mapping(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["真条件"] = leaf_condition(True, "真条件")
        ctx.leaf_executor.results["假条件"] = leaf_condition(False, "假条件")
        assert Traverser(ctx).tick(cond("真条件")) == SUCCESS
        assert Traverser(ctx).tick(cond("假条件")) == FAILURE

    def test_condition_bool_value_enters_report(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["真条件"] = leaf_condition(True, "真条件")
        Traverser(ctx).tick(cond("真条件"))
        report = ctx.reporter.exec_state().completed[0]
        assert report.node_type == "Condition"
        assert report.condition_result is True

    def test_leaf_result_error_source_recorded(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["程序失败"] = leaf_failure(
            "程序失败", source="program", terminator="fatal_error"
        )
        Traverser(ctx).tick(action("程序失败"))
        assert ctx.failure_reason is not None
        assert "程序侧失败" in ctx.failure_reason


class TestLeafTraceReport:
    """任务 3.2：叶子返回的 LeafTrace 随节点报告记录（经 M8）。"""

    def test_action_trace_in_report(self, config) -> None:
        ctx = make_run_context(config)
        trace = LeafTrace(
            llm_input={"desc": "动作"},
            llm_reasoning=["推理步骤"],
            decision="结果: 成功",
            calls=[],
        )
        ctx.leaf_executor.results["动作"] = leaf_success("动作", trace=trace)
        Traverser(ctx).tick(action("动作"))
        report = ctx.reporter.exec_state().completed[0]
        assert report.llm_trace is trace
        assert report.llm_trace.decision == "结果: 成功"
        assert report.llm_trace.llm_reasoning == ["推理步骤"]

    def test_condition_trace_in_report(self, config) -> None:
        from webops.leaf_agent.models import LeafResult

        ctx = make_run_context(config)
        trace = LeafTrace(llm_input={"desc": "条件"}, decision="结果: 真")
        ctx.leaf_executor.results["条件"] = LeafResult(
            status="success", bool_value=True, trace=trace
        )
        Traverser(ctx).tick(cond("条件"))
        report = ctx.reporter.exec_state().completed[0]
        assert report.llm_trace is trace


class TestFailurePropagation:
    """任务 3.3：叶子 FAILURE 沿树向上聚合，根统一终止并返回失败原因。"""

    def test_sequence_aggregates_leaf_failure(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results.update(
            {"ok": leaf_success("ok"), "bad": leaf_failure("bad")}
        )
        node = seq(action("ok"), action("bad"), action("ok"))
        assert Traverser(ctx).tick(node) == FAILURE
        assert ctx.failure_reason is not None
        assert "bad" in ctx.failure_reason

    def test_failure_reason_points_to_leaf_with_terminator(self, config) -> None:
        ctx = make_run_context(config)
        ctx.leaf_executor.results["bad"] = leaf_failure("bad", terminator="no_progress")
        ctx.leaf_executor.results["ok"] = leaf_success("ok")
        node = seq(action("bad"), action("ok"))
        assert Traverser(ctx).tick(node) == FAILURE
        assert "bad" in ctx.failure_reason
        assert "no_progress" in ctx.failure_reason

    def test_selector_all_fail_propagates(self, config) -> None:
        from orchestrator_helpers import branch, sel

        ctx = make_run_context(config)
        ctx.leaf_executor.results["c1"] = leaf_condition(False, "c1")
        ctx.leaf_executor.results["c2"] = leaf_condition(False, "c2")
        node = sel(
            branch(cond("c1"), action("child1")),
            branch(cond("c2"), action("child2")),
        )
        assert Traverser(ctx).tick(node) == FAILURE
        assert ctx.failure_reason is not None


class TestGlobalTimeout:
    """任务 3.4：全局 timeout 在叶子层面生效，超时置 FAILURE 并沿树传播。"""

    def _cfg(self, config, timeout):
        from webops.orchestrator import RunConfig

        return RunConfig(report_dir=config.report_dir, timeout=timeout)

    def test_blocking_leaf_timeout_marks_failure(self, config) -> None:
        cfg = self._cfg(config, 0.05)
        ctx = make_run_context(cfg, leaf_executor=BlockingLeaf(0.2))
        node = seq(action("慢动作"))
        assert Traverser(ctx).tick(node) == FAILURE
        assert "执行超时" in ctx.failure_reason
        report = ctx.reporter.exec_state().completed[0]
        assert report.result == "failure"

    def test_timeout_propagates_and_short_circuits(self, config) -> None:
        cfg = self._cfg(config, 0.05)
        ctx = make_run_context(cfg, leaf_executor=BlockingLeaf(0.2))
        node = seq(action("慢动作"), action("快动作"))
        assert Traverser(ctx).tick(node) == FAILURE
        assert len(ctx.leaf_executor.calls) == 1  # 首个超时即短路

    def test_fast_leaf_under_timeout_succeeds(self, config) -> None:
        cfg = self._cfg(config, 1.0)
        ctx = make_run_context(cfg, leaf_executor=BlockingLeaf(0.01))
        assert Traverser(ctx).tick(seq(action("快动作"))) == SUCCESS


class TestTimeoutInheritance:
    """任务 3.5：块覆盖 timeout 的叶子用覆盖值、其余用全局默认。"""

    def test_block_override_and_inheritance(self, config) -> None:
        from webops.parser.models import BlockDecl, ConfigOverride

        blocks = {
            "登录": BlockDecl(
                name="登录",
                doc_id="主流程",
                config_overrides=(ConfigOverride(name="timeout", value=0.3),),
            ),
        }
        ctx = make_run_context(config, blocks=blocks)
        node = seq(
            action("根叶子", frame="主流程/"),
            seq(action("块叶子", frame="主流程/登录/"), frame="主流程/登录/"),
            seq(action("子块叶子", frame="主流程/登录/子块/"), frame="主流程/登录/子块/"),
        )
        assert Traverser(ctx).tick(node) == SUCCESS
        # 全局默认（根级）: config.timeout = 120
        assert ctx.leaf_executor.timeouts["根叶子"] == 120.0
        # 块覆盖值: 登录块配置覆盖 timeout=0.3
        assert ctx.leaf_executor.timeouts["块叶子"] == 0.3
        # 三级继承: 子块无覆盖 → 继承最近祖先（登录块）的 0.3
        assert ctx.leaf_executor.timeouts["子块叶子"] == 0.3

    def test_block_override_used_by_blocking_leaf(self, config) -> None:
        from webops.orchestrator import RunConfig
        from webops.parser.models import BlockDecl, ConfigOverride

        blocks = {
            "登录": BlockDecl(
                name="登录",
                doc_id="主流程",
                config_overrides=(ConfigOverride(name="timeout", value=0.03),),
            ),
        }
        cfg = RunConfig(report_dir=config.report_dir, timeout=120.0)
        ctx = make_run_context(cfg, blocks=blocks, leaf_executor=BlockingLeaf(0.15))
        node = seq(seq(action("块内慢动作", frame="主流程/登录/"), frame="主流程/登录/"))
        assert Traverser(ctx).tick(node) == FAILURE
        assert "执行超时" in ctx.failure_reason
