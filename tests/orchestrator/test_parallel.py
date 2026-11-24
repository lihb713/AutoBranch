"""Parallel 节点：线程帧隔离、父帧只读、并发执行与结果收集。"""

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
from autobranch.plugins.transform import TransformPlugin
from autobranch.plugins.vars import VarsPlugin


def _registry() -> PluginRegistry:
    reg = PluginRegistry()
    reg.register(VarsPlugin())
    reg.register(ComputePlugin())
    reg.register(TransformPlugin())
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


def test_parallel_collects_rows_in_input_order(config):
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
        collect_target="rows",
        collect_fields=("result",),
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    assert ctx.space.read(ctx.current_frame, "rows") == [
        {"item": "a", "result": "a"},
        {"item": "b", "result": "b"},
        {"item": "c", "result": "c"},
    ]
    # 线程局部 result 不写父帧
    assert ctx.space.read(ctx.current_frame, "result") is None


def test_parallel_reads_parent_but_never_writes_it(config):
    ctx = make_run_context(config)
    ctx.registry = _registry()
    frame = ctx.current_frame
    ctx.space.write(frame, "items", ["a", "b"], "array")
    ctx.space.write(frame, "prefix", "P", "str")
    ctx.space.write(frame, "result", "parent", "str")
    node = ParallelNode(
        variables=(("item", "Param.items"),),
        body=FunctionCallNode(
            function="transform.concat",
            args=("Param.prefix", "Param.item"),
            returns=(("result", "str"),),
        ),
        collect_target="rows",
        collect_fields=("result",),
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    assert ctx.space.read(frame, "result") == "parent"
    assert ctx.space.read(frame, "rows") == [
        {"item": "a", "result": "Pa"},
        {"item": "b", "result": "Pb"},
    ]


def test_parallel_collects_multiple_item_dimensions(config):
    ctx = make_run_context(config)
    ctx.registry = _registry()
    frame = ctx.current_frame
    ctx.space.write(frame, "hosts", ["a", "b"], "array")
    ctx.space.write(frame, "ports", [80, 81], "array")
    node = ParallelNode(
        variables=(("host", "Param.hosts"), ("port", "Param.ports")),
        body=FunctionCallNode(
            function="vars.set",
            args=("Param.host",),
            returns=(("result", "str"),),
        ),
        collect_target="rows",
        collect_fields=("result",),
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    assert ctx.space.read(frame, "rows") == [
        {"host": "a", "port": 80, "result": "a"},
        {"host": "b", "port": 81, "result": "b"},
    ]


def test_parallel_partial_failure_policy_and_collection(config):
    def _node(on_failure: str) -> ParallelNode:
        return ParallelNode(
            variables=(("item", "Param.items"),),
            body=FunctionCallNode(
                function="compute.divide",
                args=("1", "Param.item"),
                returns=(("result", "float"),),
            ),
            on_failure=on_failure,
            collect_target="rows",
            collect_fields=("result",),
        )

    ctx = make_run_context(config)
    ctx.registry = _registry()
    ctx.space.write(ctx.current_frame, "items", [1, 0, 2], "array")
    assert Traverser(ctx).tick(_node("continue")) == SUCCESS
    assert ctx.space.read(ctx.current_frame, "rows") == [
        {"item": 1, "result": 1.0},
        {"item": 0, "result": None},
        {"item": 2, "result": 0.5},
    ]

    ctx = make_run_context(config)
    ctx.registry = _registry()
    ctx.space.write(ctx.current_frame, "items", [1, 0, 2], "array")
    assert Traverser(ctx).tick(_node("abort")) == "failure"
    # 失败整体不阻止收集：仍保留逐线程结果供排查
    assert ctx.space.read(ctx.current_frame, "rows") == [
        {"item": 1, "result": 1.0},
        {"item": 0, "result": None},
        {"item": 2, "result": 0.5},
    ]


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
