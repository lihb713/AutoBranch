"""Parallel 节点：并发执行、变量隔离/冲突与报告标签。"""

from __future__ import annotations

import threading
import time

from orchestrator_helpers import make_run_context

from autobranch.leaf_agent.models import LeafResult
from autobranch.orchestrator import SUCCESS
from autobranch.orchestrator.traverser import Traverser
from autobranch.parser.models import ActionNode, FunctionCallNode, ParallelNode
from autobranch.plugin_system import PluginRegistry
from autobranch.plugins.compute import ComputePlugin
from autobranch.plugins.vars import VarsPlugin


def _registry() -> PluginRegistry:
    reg = PluginRegistry()
    reg.register(VarsPlugin())
    reg.register(ComputePlugin())
    return reg


def test_parallel_runs_concurrently_and_labels_reports(config):
    lock = threading.Lock()
    active = 0
    max_active = 0

    def leaf(_node, _timeout):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return LeafResult(status="success")

    ctx = make_run_context(config, leaf_executor=leaf)
    ctx.space.write(ctx.current_frame, "items", [1, 2, 3, 4], "array")
    node = ParallelNode(
        variables=(("item", "Param.items"),),
        body=ActionNode(description="处理"),
        max_concurrency=2,
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    assert max_active == 2
    reports = ctx.reporter.exec_state().completed
    child_reports = [report for report in reports if report.node_type == "Action"]
    assert len(child_reports) == 4
    assert all(
        report.parallel and report.parallel.startswith("Parallel#")
        for report in child_reports
    )


def test_parallel_merges_variables_with_last_policy(config):
    ctx = make_run_context(config)
    ctx.registry = _registry()
    ctx.space.write(ctx.current_frame, "items", ["a", "b", "c"], "array")
    node = ParallelNode(
        variables=(("item", "Param.items"),),
        body=FunctionCallNode(
            function="vars.set",
            args=("Param.item",),
            returns=(("result", "str"),),
        ),
        on_conflict="last",
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    assert ctx.space.read(ctx.current_frame, "result") == "c"
    report = ctx.reporter.exec_state().completed[-1]
    assert report.node_type == "Parallel"
    assert report.details["成功"] == 3


def test_parallel_conflict_defaults_to_failure(config):
    ctx = make_run_context(config)
    ctx.registry = _registry()
    ctx.space.write(ctx.current_frame, "items", ["a", "b"], "array")
    node = ParallelNode(
        variables=(("item", "Param.items"),),
        body=FunctionCallNode(
            function="vars.set",
            args=("Param.item",),
            returns=(("result", "str"),),
        ),
    )
    assert Traverser(ctx).tick(node) == "failure"
    assert "变量写冲突" in (ctx.failure_reason or "")


def test_parallel_all_fail_with_continue_is_failure(config):
    ctx = make_run_context(config)
    ctx.space.write(ctx.current_frame, "items", ["a", "b"], "array")
    node = ParallelNode(
        variables=(("item", "Param.items"),),
        body=FunctionCallNode(function="missing.function", returns=()),
        on_failure="continue",
    )
    assert Traverser(ctx).tick(node) == "failure"
    assert ctx.failure_reason is not None


def test_parallel_partial_failure_policy(config):
    def _node(on_failure: str) -> ParallelNode:
        return ParallelNode(
            variables=(("item", "Param.items"),),
            body=FunctionCallNode(
                function="compute.divide",
                args=("1", "Param.item"),
                returns=(("result", "float"),),
            ),
            on_failure=on_failure,
            on_conflict="last",
        )

    ctx = make_run_context(config)
    ctx.registry = _registry()
    ctx.space.write(ctx.current_frame, "items", [1, 0, 2], "array")
    assert Traverser(ctx).tick(_node("continue")) == SUCCESS
    assert ctx.space.read(ctx.current_frame, "result") == 0.5

    ctx = make_run_context(config)
    ctx.registry = _registry()
    ctx.space.write(ctx.current_frame, "items", [1, 0, 2], "array")
    assert Traverser(ctx).tick(_node("abort")) == "failure"
