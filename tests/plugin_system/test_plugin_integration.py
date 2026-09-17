"""插件集成（组 4）：FunctionCall 节点遍历 / 叶子两级能力选择 / 变量落笔。"""

from __future__ import annotations

from fake_transport import FakeTransport, chat_response
from leaf_agent_helpers import make_session_factory, tool_call

from autobranch.leaf_agent import execute_leaf
from autobranch.leaf_agent.models import LeafContext
from autobranch.llm import LLMConfig
from autobranch.orchestrator.context import RunContext
from autobranch.orchestrator.models import RunConfig
from autobranch.orchestrator.traverser import Traverser
from autobranch.parser.models import ActionNode, FunctionCallNode
from autobranch.plugin_system import (
    PluginBase,
    PluginRegistry,
    PluginRuntime,
    engine_function,
)
from autobranch.plugins.compute import ComputePlugin
from autobranch.schema import SchemaSpace


class _FakeReporter:
    def __init__(self) -> None:
        self.reports = []

    def start_node(self, info):
        pass

    def record_node(self, report):
        self.reports.append(report)

    def capture_screenshot(self, ref, desc):
        return ""


def test_function_call_node_tick_compute():
    reg = PluginRegistry()
    reg.register(ComputePlugin())
    space = SchemaSpace()
    frame = space.enter_frame("t", None)
    ctx = RunContext(
        config=RunConfig(),
        space=space,
        reporter=_FakeReporter(),
        browser=None,
        leaf_executor=lambda n, t: None,
        registry=reg,
        runtime=PluginRuntime(),
    )
    node = FunctionCallNode(
        function="compute.multiply", args=("2", "3"), returns=(("结果", "int"),)
    )
    status = Traverser(ctx).tick(node)
    assert status == "success"
    assert space.read(frame, "结果") == 6


def test_function_call_unknown_function_fails():
    reg = PluginRegistry()
    reg.register(ComputePlugin())
    space = SchemaSpace()
    space.enter_frame("t", None)
    ctx = RunContext(
        config=RunConfig(),
        space=space,
        reporter=_FakeReporter(),
        browser=None,
        leaf_executor=lambda n, t: None,
        registry=reg,
        runtime=PluginRuntime(),
    )
    node = FunctionCallNode(function="nope", args=())
    status = Traverser(ctx).tick(node)
    assert status == "failure"
    assert ctx.failure_reason and "nope" in ctx.failure_reason


def _leaf_ctx(fake, registry, space):
    return LeafContext(
        config=LLMConfig(base_url="http://x", api_key="k", model="m"),
        space=space,
        session_factory=make_session_factory(fake),
        registry=registry,
        runtime=PluginRuntime(),
    )


def test_plugin_leaf_two_level_capability_no_prefetch():
    reg = PluginRegistry()
    reg.register(ComputePlugin())
    fake = FakeTransport(
        responses=[
            chat_response(tool_calls=[tool_call("use_capability", {"capability": "compute"})]),
            chat_response(tool_calls=[tool_call("compute__multiply", {"a": 2, "b": 3})]),
            chat_response(text="结果: 成功"),
        ]
    )
    space = SchemaSpace()
    space.enter_frame("t", None)
    ctx = _leaf_ctx(fake, reg, space)
    node = ActionNode(description="计算 2 乘 3")
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    # 插件模式不强制预取语义图（工具集不应含 semantic_graph）
    tool_names = {
        t["function"]["name"]
        for r in fake.requests
        for t in (r.json().get("tools", []) or [])
    }
    assert "browser.semantic_graph" not in tool_names
    # 首次请求工具集含 use_capability
    first = fake.requests[0].json()
    assert any("use_capability" in str(t) for t in first.get("tools", []))


class _EchoPlugin(PluginBase):
    name = "echo"
    description = "回声插件"

    @engine_function(
        name="produce",
        description="产出值（产出型）",
        output_param="target",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string", "description": "值"}},
            "required": ["value"],
        },
        returns=("v",),
    )
    def produce(self, value):
        return value


def test_plugin_leaf_producing_write_variable():
    reg = PluginRegistry()
    reg.register(_EchoPlugin())
    fake = FakeTransport(
        responses=[
            chat_response(tool_calls=[tool_call("use_capability", {"capability": "echo"})]),
            chat_response(
                tool_calls=[tool_call("echo.produce", {"value": "hi", "target": "result"})]
            ),
            chat_response(text="结果: 成功"),
        ]
    )
    space = SchemaSpace()
    frame = space.enter_frame("t", None)
    ctx = _leaf_ctx(fake, reg, space)
    node = ActionNode(
        description="把 hi 写入变量结果 NewParam.result:str",
        set_targets=("result",),
        set_decls=(("result", "str"),),
    )
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    assert space.read(frame, "result") == "hi"


def test_plugin_leaf_producing_undeclared_rejected():
    reg = PluginRegistry()
    reg.register(_EchoPlugin())
    fake = FakeTransport(
        responses=[
            chat_response(tool_calls=[tool_call("use_capability", {"capability": "echo"})]),
            chat_response(
                tool_calls=[tool_call("echo.produce", {"value": "hi", "target": "未声明"})]
            ),
            chat_response(text="结果: 失败"),
        ]
    )
    space = SchemaSpace()
    space.enter_frame("t", None)
    ctx = _leaf_ctx(fake, reg, space)
    node = ActionNode(description="产出")
    result = execute_leaf(node, ctx)
    # 落笔目标未声明 → 工具结果报错，LLM 最终只能失败
    assert result.status == "failure"
    assert any("未在叶子可写变量集内" in r.result for r in result.trace.calls)
