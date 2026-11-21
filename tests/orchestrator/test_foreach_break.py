"""ForEach break_on_success 与参数点路径读取。"""

from __future__ import annotations

from orchestrator_helpers import make_run_context

from autobranch.orchestrator import SUCCESS
from autobranch.orchestrator.traverser import Traverser
from autobranch.parser.models import ForEachNode, FunctionCallNode
from autobranch.plugin_system import PluginRegistry
from autobranch.plugins.predicate import PredicatePlugin
from autobranch.plugins.vars import VarsPlugin


def _registry() -> PluginRegistry:
    reg = PluginRegistry()
    reg.register(VarsPlugin())
    reg.register(PredicatePlugin())
    return reg


def test_foreach_break_on_success(config):
    ctx = make_run_context(config)
    ctx.registry = _registry()
    space = ctx.space
    frame = ctx.current_frame
    space.write(frame, "items", ["a", "b", "c"], "array")
    node = ForEachNode(
        variables=(("item", "Param.items"),),
        body=FunctionCallNode(
            function="vars.set",
            args=("Param.item",),
            returns=(("last", "str"),),
        ),
        break_on_success=True,
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    assert space.read(frame, "last") == "a"
    report = ctx.reporter.exec_state().completed[-1]
    assert report.details["提前终止"] == 1


def test_foreach_without_break_keeps_last_success(config):
    ctx = make_run_context(config)
    ctx.registry = _registry()
    frame = ctx.current_frame
    ctx.space.write(frame, "items", ["a", "b", "c"], "array")
    node = ForEachNode(
        variables=(("item", "Param.items"),),
        body=FunctionCallNode(
            function="vars.set",
            args=("Param.item",),
            returns=(("last", "str"),),
        ),
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    assert ctx.space.read(frame, "last") == "c"


def test_param_dot_path_in_function_args(config):
    ctx = make_run_context(config)
    ctx.registry = _registry()
    frame = ctx.current_frame
    ctx.space.write(frame, "obj", {"name": {"value": "alice"}}, "object")
    node = FunctionCallNode(
        function="vars.set",
        args=("Param.obj.name.value",),
        returns=(("name", "str"),),
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    assert ctx.space.read(frame, "name") == "alice"


def test_param_dot_path_missing_fails(config):
    ctx = make_run_context(config)
    ctx.registry = _registry()
    ctx.space.write(ctx.current_frame, "obj", {"name": "alice"}, "object")
    node = FunctionCallNode(
        function="vars.set",
        args=("Param.obj.missing",),
        returns=(("name", "str"),),
    )
    assert Traverser(ctx).tick(node) == "failure"
