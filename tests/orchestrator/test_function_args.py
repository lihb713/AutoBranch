"""FunctionCall 参数字面量：空白保留与原生 dict/list 求值。"""

from __future__ import annotations

from orchestrator_helpers import make_run_context

from autobranch.orchestrator import SUCCESS
from autobranch.orchestrator.traverser import Traverser
from autobranch.parser.models import FunctionCallNode
from autobranch.plugin_system import PluginRegistry
from autobranch.plugins.transform import TransformPlugin


def _context(config):
    ctx = make_run_context(config)
    reg = PluginRegistry()
    reg.register(TransformPlugin())
    ctx.registry = reg
    return ctx


def test_string_literal_keeps_trailing_space(config):
    ctx = _context(config)
    frame = ctx.current_frame
    ctx.space.write(frame, "env", "demo.com", "str")
    node = FunctionCallNode(
        function="transform.concat",
        args=("python3 /tmp/get_vms.py ", "Param.env"),
        returns=(("cmd", "str"),),
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    assert ctx.space.read(frame, "cmd") == "python3 /tmp/get_vms.py demo.com"


def test_separator_space_literal_preserved(config):
    ctx = _context(config)
    node = FunctionCallNode(
        function="transform.concat",
        args=("a", "b"),
        kwargs=(("separator", " "),),
        returns=(("text", "str"),),
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    assert ctx.space.read(ctx.current_frame, "text") == "a b"


def test_dict_positional_arg_is_evaluated_recursively(config):
    ctx = _context(config)
    frame = ctx.current_frame
    ctx.space.write(frame, "env", "demo.com", "str")
    node = FunctionCallNode(
        function="transform.format",
        args=("python3 get_vms.py --region={region}", {"region": "Param.env"}),
        returns=(("cmd", "str"),),
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    assert ctx.space.read(frame, "cmd") == "python3 get_vms.py --region=demo.com"


def test_parsed_dict_arg_runs_end_to_end(config):
    from autobranch.parser import parse
    from autobranch.parser.models import DocumentSource, FunctionCallNode

    ctx = _context(config)
    result = parse(
        DocumentSource(
            id="t",
            data="""tree: t
inputs: {env: str}
nodes:
  r: {type: Root, body: n1}
  n1:
    type: FunctionCall
    function: transform.format
    args:
      - "python3 get_vms.py --region={region}"
      - region: Param.env
    returns: {cmd: str}
root: r
""",
        ),
        None,
        function_registry=ctx.registry,
    )
    assert result.checks.ok, result.checks.issues
    call = result.tree.root.children[0]
    assert isinstance(call, FunctionCallNode)
    assert call.args[1] == {"region": "Param.env"}
    ctx.space.write(ctx.current_frame, "env", "demo.com", "str")
    assert Traverser(ctx).tick(call) == SUCCESS
    assert ctx.space.read(ctx.current_frame, "cmd") == "python3 get_vms.py --region=demo.com"
