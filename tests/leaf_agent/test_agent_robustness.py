"""叶子 agent 鲁棒性：LLM 畸形输出纠错重试 + 能力概览注入（参数语法重构后的稳定性增强）。"""

from __future__ import annotations

from fake_transport import chat_response
from leaf_agent_helpers import make_ctx, tool_call

from autobranch.leaf_agent import execute_leaf
from autobranch.parser.models import ActionNode


def test_protocol_error_retries_in_loop(config, fake, stub_engine):
    """工具调用参数非法 JSON → 协议错误：回填纠错后预算内重试成功，而非终止叶子。"""
    bad_call = {
        "id": "call_bad",
        "type": "function",
        "function": {"name": "browser.semantic_graph", "arguments": '{"scope": [1]'},
    }
    fake.responses = [
        chat_response(tool_calls=[bad_call]),
        chat_response(
            tool_calls=[tool_call("browser.semantic_graph", {"scope": "full", "lod": 2})]
        ),
        chat_response(text="结果: 成功"),
    ]
    stub_engine.results["browser.semantic_graph"] = {"ok": True, "detail": {"text": "PAGE: 测试"}}
    result = execute_leaf(
        ActionNode(description="点击登录"), make_ctx(config, fake, stub_engine)
    )
    assert result.status == "success"


def test_decision_error_retries_in_loop(config, fake, stub_engine):
    """最终回答不含结果标记（DecisionError）→ 回填纠错后预算内重试成功。"""
    fake.responses = [
        chat_response(text="随便说点什么"),
        chat_response(text="结果: 成功"),
    ]
    result = execute_leaf(
        ActionNode(description="点击登录"), make_ctx(config, fake, stub_engine)
    )
    assert result.status == "success"
    assert fake.last_request is not None


def test_repeated_protocol_error_bounded(config, fake, stub_engine):
    """畸形输出反复出现：受轮次限制终止（llm 侧），不死循环。"""
    bad_call = {
        "id": "call_bad",
        "type": "function",
        "function": {"name": "browser.semantic_graph", "arguments": "nope"},
    }
    fake.responses = [
        chat_response(tool_calls=[bad_call]),
        chat_response(tool_calls=[bad_call]),
        chat_response(tool_calls=[bad_call]),
        chat_response(tool_calls=[bad_call]),
    ]
    result = execute_leaf(
        ActionNode(description="点击登录"),
        make_ctx(config, fake, stub_engine, max_rounds=3),
    )
    assert result.status == "failure"
    assert result.error_source == "llm"
    assert result.trace.terminator == "round_limit"


def test_capability_overview_injected(config, fake, stub_engine):
    """能力概览注入系统提示：LLM 可见精确的可用能力名（避免臆造）。"""
    stub_engine.register_plugin("browser", "浏览器自动化")
    stub_engine.register_plugin("compute", "计算")
    fake.responses = [chat_response(text="结果: 成功")]
    execute_leaf(ActionNode(description="访问网站"), make_ctx(config, fake, stub_engine))
    body = fake.last_request.json()
    system = body["messages"][0]["content"]
    assert "可用能力: browser, compute" in system
    assert "能力名" in system or "use_capability" in system


def test_capability_overview_empty_ok(config, fake, stub_engine):
    """无插件时概览为占位文本，不阻断执行。"""
    fake.responses = [chat_response(text="结果: 成功")]
    result = execute_leaf(
        ActionNode(description="点击登录"),
        make_ctx(config, fake, stub_engine),
    )
    assert result.status == "success"
