"""M6 叶子变量读取替换测试（参数语法重构：Param.x 确定性替换）。

叶子执行前，``Param.x`` 被程序从 blackboard 读取替换为真实值注入 LLM；
未定义读取 → 叶子直接 FAILURE（程序侧）；反引号转义段不替换。
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
    """``Param.amount`` 被替换为 blackboard 真实值。"""
    space.write(space._current, "this/amount", 98.0, "float")
    transport = FakeTransport(responses=[chat_response(text="结果: 成功")])
    ctx, _ = _ctx(llm_config, space, transport)
    node = ActionNode(description="填金额 Param.amount")
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    body = transport.last_request.json()
    joined = " ".join(m["content"] for m in body["messages"])
    assert "98.0" in joined
    assert "Param." not in joined


def test_get_undefined_fails_leaf(llm_config, space):
    """``Param.nope`` 变量未定义 → 叶子直接 FAILURE（程序侧）。"""
    transport = FakeTransport(responses=[chat_response(text="结果: 成功")])
    ctx, _ = _ctx(llm_config, space, transport)
    node = ActionNode(description="读 Param.nope")
    result = execute_leaf(node, ctx)
    assert result.status == "failure"
    assert result.error_source == "program"
    assert "未定义" in (result.trace.decision or "")
    # 未触发任何 LLM 请求
    assert transport.requests == []


def test_get_backtick_escaped_not_replaced(llm_config, space):
    """反引号转义的 `` `Param` `` 不替换、去反引号；同描述内的 Param.amount 仍替换。"""
    space.write(space._current, "this/amount", 98.0, "float")
    transport = FakeTransport(responses=[chat_response(text="结果: 成功")])
    ctx, _ = _ctx(llm_config, space, transport)
    node = ActionNode(description="写 `Param` 保留字，读 Param.amount")
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    body = transport.last_request.json()
    joined = " ".join(m["content"] for m in body["messages"])
    assert "写 Param 保留字" in joined
    assert "98.0" in joined


def test_condition_get_replaced(llm_config, space):
    """Condition 描述中的 ``Param.status`` 也被替换。"""
    space.write(space._current, "this/status", "已批准", "str")
    transport = FakeTransport(responses=[chat_response(text="结果: 真")])
    ctx, _ = _ctx(llm_config, space, transport)
    node = ConditionNode(description="状态是 Param.status")
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    assert result.bool_value is True
    body = transport.last_request.json()
    joined = " ".join(m["content"] for m in body["messages"])
    assert "已批准" in joined


def test_extract_target_must_be_declared(llm_config, space):
    """extract 目标不在叶子 NewParam. 声明集内 → 拒绝（不写入）。"""
    from fake_transport import chat_response as _chat

    tool_call = {
        "id": "c1",
        "type": "function",
        "function": {
            "name": "browser.extract",
            "arguments": '{"ref":"[1]","target":"undeclared"}',
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
    engine.results["browser.extract"] = {"ok": True, "detail": {"var": "undeclared", "value": "x"}}

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
    node = ActionNode(description="提取值 NewParam.declared", set_targets=("declared",))
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    extract_calls = [c for c in engine.calls if c[0] == "browser.extract"]
    assert extract_calls == []


def test_extract_target_declared_allowed(llm_config, space):
    """extract 目标在 NewParam. 声明集内 → 正常调用引擎 extract。"""
    from fake_transport import chat_response as _chat

    from autobranch.browser import OpResult

    tool_call = {
        "id": "c1",
        "type": "function",
        "function": {
            "name": "browser.extract",
            "arguments": '{"ref":"[1]","target":"declared"}',
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
        True, detail={"var": "declared", "value": "x", "type": "str"}
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
    node = ActionNode(description="提取 NewParam.declared", set_targets=("declared",))
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    extract_calls = [c for c in engine.calls if c[0] == "browser.extract"]
    assert len(extract_calls) == 1
    assert "target" not in extract_calls[0][1]


def test_open_save_to_must_be_declared(llm_config, space):
    """open 的 save_to 目标未在叶子 NewParam. 声明集内 → 拒绝（不写入）。"""
    from fake_transport import chat_response as _chat

    from autobranch.browser import OpResult

    tool_call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "browser.open", "arguments": '{"url":"http://x","save_to":"undeclaredPage"}'},
    }
    transport = FakeTransport(
        responses=[
            _chat(text="", tool_calls=[tool_call]),
            _chat(text="结果: 成功"),
        ]
    )
    engine = MockRegistry()
    engine.register("browser.open", output_param="save_to")
    engine.results["browser.open"] = OpResult(True, detail={"page_ref": "p", "var": "undeclaredPage"})

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
        description="开页面 NewParam.declaredPage:page_ref",
        set_targets=("declaredPage",),
        set_decls=(("declaredPage", "page_ref"),),
    )
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    open_calls = [c for c in engine.calls if c[0] == "browser.open"]
    assert open_calls == []


def test_open_save_to_declared_allowed(llm_config, space):
    """open 的 save_to 在声明集内 → 正常调用。"""
    from fake_transport import chat_response as _chat

    from autobranch.browser import OpResult

    tool_call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "browser.open", "arguments": '{"url":"http://x","save_to":"pageA"}'},
    }
    transport = FakeTransport(
        responses=[
            _chat(text="", tool_calls=[tool_call]),
            _chat(text="结果: 成功"),
        ]
    )
    engine = MockRegistry()
    engine.register("browser.open", output_param="save_to")
    engine.results["browser.open"] = OpResult(True, detail={"page_ref": "p", "var": "pageA"})

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
        description="开 NewParam.pageA:page_ref",
        set_targets=("pageA",),
        set_decls=(("pageA", "page_ref"),),
    )
    result = execute_leaf(node, ctx)
    assert result.status == "success"
    open_calls = [c for c in engine.calls if c[0] == "browser.open"]
    assert len(open_calls) == 1
    assert "save_to" not in open_calls[0][1]