"""ForEach 运行时遍历测试。"""

from __future__ import annotations

from autobranch.leaf_agent.models import LeafResult
from autobranch.orchestrator.context import RunContext
from autobranch.orchestrator.models import FAILURE, SUCCESS, RunConfig
from autobranch.orchestrator.traverser import Traverser
from autobranch.parser.models import ActionNode, ForEachNode, FunctionCallNode
from autobranch.plugin_system import PluginRegistry, PluginRuntime
from autobranch.plugins.transform import TransformPlugin
from autobranch.schema import SchemaSpace


class _Reporter:
    def __init__(self) -> None:
        self.reports = []

    def start_node(self, info):
        pass

    def record_node(self, report):
        self.reports.append(report)

    def capture_screenshot(self, ref, desc):
        return ""


def _context(leaf):
    space = SchemaSpace()
    frame = space.enter_frame("t", None)
    space.write(frame, "env_ids", ["a", "b", "c"], "array")
    ctx = RunContext(
        config=RunConfig(),
        space=space,
        reporter=_Reporter(),
        browser=None,
        leaf_executor=leaf,
        registry=PluginRegistry(),
        runtime=PluginRuntime(),
    )
    return ctx, space


def test_foreach_iterates_items_and_scalars_in_temp_frame():
    seen: list[tuple[str, str]] = []

    def leaf(node, _timeout):
        frame = ctx.space._current
        seen.append((
            ctx.space.read(frame, "env_id"),
            ctx.space.read(frame, "label"),
        ))
        return LeafResult(status="success")

    ctx, _ = _context(leaf)
    node = ForEachNode(
        variables=(("env_id", "Param.env_ids"), ("label", "x")),
        body=ActionNode(description="处理 Param.env_id"),
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    assert seen == [("a", "x"), ("b", "x"), ("c", "x")]


def test_foreach_continue_and_abort():
    def leaf(_node, _timeout):
        frame = ctx.space._current
        return LeafResult(
            status="failure" if ctx.space.read(frame, "env_id") == "b" else "success"
        )

    ctx, _ = _context(leaf)
    continue_node = ForEachNode(
        variables=(("env_id", "Param.env_ids"),),
        body=ActionNode(description="处理"),
        on_failure="continue",
    )
    assert Traverser(ctx).tick(continue_node) == SUCCESS
    assert ctx.failure_reason is None

    ctx, _ = _context(leaf)
    abort_node = ForEachNode(
        variables=(("env_id", "Param.env_ids"),),
        body=ActionNode(description="处理"),
        on_failure="abort",
    )
    assert Traverser(ctx).tick(abort_node) == FAILURE
    assert ctx.failure_reason is not None


def test_foreach_collect_results_with_transform_append():
    space = SchemaSpace()
    frame = space.enter_frame("t", None)
    space.write(frame, "items", ["a", "b"], "array")
    space.write(frame, "results", "", "str")
    reg = PluginRegistry()
    reg.register(TransformPlugin())
    ctx = RunContext(
        config=RunConfig(),
        space=space,
        reporter=_Reporter(),
        browser=None,
        leaf_executor=lambda _n, _t: LeafResult(status="success"),
        registry=reg,
        runtime=PluginRuntime(),
    )
    node = ForEachNode(
        variables=(("item", "Param.items"),),
        body=FunctionCallNode(
            function="transform.append",
            args=("Param.results", "Param.item"),
            returns=(("results", "str"),),
        ),
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    assert space.read(frame, "results") == '["a", "b"]'


def test_foreach_mismatched_list_lengths_fails():
    ctx, space = _context(lambda _n, _t: LeafResult(status="success"))
    frame = space._current
    space.write(frame, "other", ["x"], "array")
    node = ForEachNode(
        variables=(("a", "Param.env_ids"), ("b", "Param.other")),
        body=ActionNode(description="处理"),
    )
    assert Traverser(ctx).tick(node) == FAILURE
    assert "长度不一致" in (ctx.failure_reason or "")


def test_foreach_continue_all_fail_returns_failure():
    ctx, _ = _context(lambda _n, _t: LeafResult(status="failure"))
    node = ForEachNode(
        variables=(("env_id", "Param.env_ids"),),
        body=ActionNode(description="处理"),
        on_failure="continue",
    )
    assert Traverser(ctx).tick(node) == FAILURE
    assert ctx.failure_reason is not None
