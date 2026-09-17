"""M6 叶子 get 变量替换测试（§5.3 读取确定性替换）。

叶子执行前，[[get:this/path]] 被程序从 blackboard 读取替换为真实值注入 LLM；
未定义/越权读取 → 叶子直接 FAILURE（程序侧）。
"""

from __future__ import annotations

import pytest
from fake_transport import FakeTransport, chat_response
from leaf_agent_helpers import MockRegistry

from autobranch.leaf_agent import execute_leaf
from autobranch.leaf_agent.models import LeafContext
from autobranch.llm import LLMConfig, LLMSession
from autobranch.parser.models import ActionNode, ConditionNode
from autobranch.schema import SchemaSpace


@pytest.fixture
def llm_config() -> LLMConfig:
    return LLMConfig(base_url="https://api.test.example/v1", api_key="sk-test", model="m")


@pytest.fixture
def space() -> SchemaSpace:
    sp = SchemaSpace()
    sp.enter_frame("主流程")
    return sp


def _ctx(llm_config, space, transport):
    engine = MockRegistry()
    session_log: list[str] = []

    def factory(cfg, system_prompt):
        return LLMSession(config=cfg, system_prompt=system_prompt, transport=transport)

    return (
        LeafContext(config=llm_config, registry=engine, space=space, session_factory=factory),
        session_log,
    )


def test_get_replaced_with_real_value(llm_config, space):
    """[[get:this/amount]] 被替换为 blackboard 真实值。"""
    space.write(space._current, "this/amount", 98.0, "float")
    transport = FakeTransport(responses=[chat_response(text="结果: 成功")])
    ctx, _ = _ctx(llm_config, space, transport)
    node = ActionNode(description="填金额 [[get:this/amount]]")
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    # 验证 LLM 收到替换后的真实值（请求体含 98.00）
    body = transport.last_request.json()
    joined = " ".join(m["content"] for m in body["messages"])
    assert "98.0" in joined
    assert "[[get:" not in joined


def test_get_undefined_fails_leaf(llm_config, space):
    """[[get:this/未定义]] 变量未定义 → 叶子直接 FAILURE（程序侧）。"""
    transport = FakeTransport(responses=[chat_response(text="结果: 成功")])
    ctx, _ = _ctx(llm_config, space, transport)
    node = ActionNode(description="读 [[get:this/未定义]]")
    result = execute_leaf(node, ctx)
    assert result.status == "failure"
    assert result.error_source == "program"
    assert "未定义" in (result.trace.decision or "")
    # 未触发任何 LLM 请求
    assert transport.requests == []


def test_get_out_of_scope_fails_leaf(llm_config, space):
    """[[get:this/兄弟/值]] 越权读取 → 叶子直接 FAILURE（程序侧）。"""
    sp = space  # fixture 已 enter_frame 主流程
    sp.enter_frame("子块A")
    sp.exit_frame()
    sp.enter_frame("兄弟")
    # 当前帧是"兄弟"，读"子块A/值"（兄弟级）应越权
    transport = FakeTransport(responses=[chat_response(text="结果: 成功")])
    ctx, _ = _ctx(llm_config, sp, transport)
    node = ActionNode(description="读 [[get:this/子块A/值]]")
    result = execute_leaf(node, ctx)
    assert result.status == "failure"
    assert result.error_source == "program"


def test_condition_get_replaced(llm_config, space):
    """Condition 描述中的 [[get:this/status]] 也被替换。"""
    space.write(space._current, "this/status", "已批准", "str")
    transport = FakeTransport(responses=[chat_response(text="结果: 真")])
    ctx, _ = _ctx(llm_config, space, transport)
    node = ConditionNode(description="状态是 [[get:this/status]]")
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    assert result.bool_value is True
    body = transport.last_request.json()
    joined = " ".join(m["content"] for m in body["messages"])
    assert "已批准" in joined


def test_extract_target_must_be_declared(llm_config, space):
    """extract 目标不在叶子 [[set:]] 声明集内 → 拒绝（不写入）。"""
    # mock LLM: 第一轮请求工具 extract 到未声明变量
    from fake_transport import chat_response as _chat

    tool_call = {
        "id": "c1",
        "type": "function",
        "function": {
            "name": "browser.extract",
            "arguments": '{"ref":"[1]","target":"this/未声明"}',
        },
    }
    transport = FakeTransport(
        responses=[
            _chat(text="", tool_calls=[tool_call]),
            _chat(text="结果: 成功"),
        ]
    )
    # MockRegistry 支持 extract 调用
    engine = MockRegistry()
    engine.register("browser.extract", output_param="target")
    engine.results["browser.extract"] = {"ok": True, "detail": {"var": "this/未声明", "value": "x"}}

    def factory(cfg, system_prompt):
        return LLMSession(config=cfg, system_prompt=system_prompt, transport=transport)

    ctx = LeafContext(
        config=llm_config,
        registry=engine,
        space=space,
        session_factory=factory,
        tools=[
            __import__("autobranch.llm", fromlist=["ToolSpec"]).ToolSpec("browser.extract", "e", {})
        ],
    )
    node = ActionNode(description="提取值 [[set:this/已声明]]", set_targets=("this/已声明",))
    result = execute_leaf(node, ctx)
    # 目标未声明 → extract 被拒（工具结果回传），但 LLM 修正后仍可成功
    assert result.status == "success"
    # 引擎层 extract 未被真正调用（校验在 M6 层拦截；仅预取 semantic_graph）
    extract_calls = [c for c in engine.calls if c[0] == "browser.extract"]
    assert extract_calls == []


def test_extract_target_declared_allowed(llm_config, space):
    """extract 目标在 [[set:]] 声明集内 → 正常调用引擎 extract。"""
    from fake_transport import chat_response as _chat

    from autobranch.browser import OpResult

    tool_call = {
        "id": "c1",
        "type": "function",
        "function": {
            "name": "browser.extract",
            "arguments": '{"ref":"[1]","target":"this/已声明"}',
        },
    }
    transport = FakeTransport(
        responses=[
            _chat(text="", tool_calls=[tool_call]),
            _chat(text="结果: 成功"),
        ]
    )
    engine = MockRegistry()
    engine.register("browser.extract", output_param="target")
    engine.results["browser.extract"] = OpResult(
        True, detail={"var": "this/已声明", "value": "x", "type": "str"}
    )

    def factory(cfg, system_prompt):
        return LLMSession(config=cfg, system_prompt=system_prompt, transport=transport)

    ctx = LeafContext(
        config=llm_config,
        registry=engine,
        space=space,
        session_factory=factory,
        tools=[],
    )
    node = ActionNode(description="提取 [[set:this/已声明]]", set_targets=("this/已声明",))
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    extract_calls = [c for c in engine.calls if c[0] == "browser.extract"]
    assert len(extract_calls) == 1
    # 产出型目标参数由引擎拆出落笔，不传给插件函数
    assert "target" not in extract_calls[0][1]

def test_open_save_to_must_be_declared(llm_config, space):
    """open 的 save_to 目标未在叶子 [[set:]] 声明集内 → 拒绝（不写入）。"""
    from fake_transport import chat_response as _chat

    from autobranch.browser import OpResult

    tool_call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "browser.open", "arguments": '{"url":"http://x","save_to":"this/未声明页"}'},
    }
    transport = FakeTransport(
        responses=[
            _chat(text="", tool_calls=[tool_call]),
            _chat(text="结果: 成功"),
        ]
    )
    engine = MockRegistry()
    engine.register("browser.open", output_param="save_to")
    engine.results["browser.open"] = OpResult(
        True, detail={"page_ref": "p", "var": "this/未声明页"}
    )

    def factory(cfg, system_prompt):
        return LLMSession(config=cfg, system_prompt=system_prompt, transport=transport)

    ctx = LeafContext(
        config=llm_config,
        registry=engine,
        space=space,
        session_factory=factory,
        tools=[],
    )
    node = ActionNode(
        description="开页面 [[set:page_ref:this/声明页]]",
        set_targets=("this/声明页",),
        set_decls=(("this/声明页", "page_ref"),),
    )
    result = execute_leaf(node, ctx)
    # 未声明目标 → open 被 M6 拒（工具结果回传），但 LLM 修正后成功
    assert result.status == "success"
    open_calls = [c for c in engine.calls if c[0] == "browser.open"]
    assert open_calls == []  # open 未真正调用（save_to 未声明被拦截）


def test_open_save_to_declared_allowed(llm_config, space):
    """open 的 save_to 在声明集内 → 正常调用。"""
    from fake_transport import chat_response as _chat

    from autobranch.browser import OpResult

    tool_call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "browser.open", "arguments": '{"url":"http://x","save_to":"this/页面A"}'},
    }
    transport = FakeTransport(
        responses=[
            _chat(text="", tool_calls=[tool_call]),
            _chat(text="结果: 成功"),
        ]
    )
    engine = MockRegistry()
    engine.register("browser.open", output_param="save_to")
    engine.results["browser.open"] = OpResult(True, detail={"page_ref": "p", "var": "this/页面A"})

    def factory(cfg, system_prompt):
        return LLMSession(config=cfg, system_prompt=system_prompt, transport=transport)

    ctx = LeafContext(
        config=llm_config,
        registry=engine,
        space=space,
        session_factory=factory,
        tools=[],
    )
    node = ActionNode(
        description="开 [[set:page_ref:this/页面A]]",
        set_targets=("this/页面A",),
        set_decls=(("this/页面A", "page_ref"),),
    )
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    open_calls = [c for c in engine.calls if c[0] == "browser.open"]
    assert len(open_calls) == 1
    # 产出型目标参数由引擎拆出落笔，不传给插件函数
    assert "save_to" not in open_calls[0][1]
