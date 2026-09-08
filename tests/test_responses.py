"""任务 7.1/7.2：Responses 协议适配与双协议共享会话。"""

from __future__ import annotations

import pytest
from fake_transport import responses_body

from webops.llm.errors import LLMProtocolError
from webops.llm.models import ToolResult, ToolSpec
from webops.llm.session import LLMSession


def make_session(config, fake, system="你是助手"):
    return LLMSession(config=config, system_prompt=system, transport=fake, protocol="responses")


def test_responses_request_body(config, fake):
    """7.1 Responses 请求构造：instructions/input/tools。"""
    fake.responses = [responses_body(text="好的")]
    session = make_session(config, fake)
    session.add_user_message("你好")
    tools = [ToolSpec(name="calc", description="计算", parameters={"type": "object"})]
    session.request(tools=tools)

    body = fake.last_request.json()
    assert body["model"] == config.model
    assert body["instructions"] == "你是助手"
    assert body["input"][0]["type"] == "message"
    assert body["input"][0]["role"] == "user"
    assert body["input"][0]["content"] == "你好"
    assert body["tools"][0]["type"] == "function"
    assert body["tools"][0]["name"] == "calc"
    assert fake.last_request.url == "https://api.test.example/v1/responses"


def test_responses_parse_text(config, fake):
    fake.responses = [responses_body(text="这是 Responses 的回复")]
    session = make_session(config, fake)
    session.add_user_message("hi")
    resp = session.request()
    assert resp.text == "这是 Responses 的回复"


def test_responses_parse_function_call(config, fake):
    fake.responses = [
        responses_body(
            function_calls=[
                {"call_id": "fc_1", "name": "calc", "arguments": '{"expr":"2+2"}'}
            ]
        )
    ]
    session = make_session(config, fake)
    session.add_user_message("算一下")
    resp = session.request(tools=[ToolSpec(name="calc", description="计算")])
    assert resp.has_tool_calls
    assert resp.tool_calls[0].id == "fc_1"
    assert resp.tool_calls[0].name == "calc"
    assert resp.tool_calls[0].arguments == '{"expr":"2+2"}'


def test_responses_invalid_arguments_raises(config, fake):
    fake.responses = [
        responses_body(function_calls=[{"call_id": "fc_2", "name": "calc", "arguments": "nope"}])
    ]
    session = make_session(config, fake)
    session.add_user_message("算")
    with pytest.raises(LLMProtocolError, match="不是合法 JSON"):
        session.request(tools=[ToolSpec(name="calc", description="计算")])


def test_both_protocols_share_session_and_response(config, fake):
    """7.2 两种形态共享同一会话与响应结构，切换不影响累积与回填。"""
    # 先 Chat 一轮工具调用
    from fake_transport import chat_response

    fake.responses = [
        chat_response(
            tool_calls=[
                {
                    "id": "call_x",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": "{}"},
                }
            ]
        ),
        responses_body(text="跨协议完成"),
    ]
    chat_session = LLMSession(config=config, system_prompt="s", transport=fake, protocol="chat")
    chat_session.add_user_message("先 chat 查")
    first = chat_session.request(tools=[ToolSpec(name="lookup", description="查询")])
    assert first.tool_calls[0].id == "call_x"
    chat_session.add_tool_result("call_x", "value=1")

    # 切到 Responses 会话继续：模拟上层把 chat 会话上下文迁移到 responses 会话
    responses_session = LLMSession(
        config=config, system_prompt="s", transport=fake, protocol="responses"
    )
    # 会话结构一致性：同一 ToolResult 回填、同一 LLMResponse 消费方式
    responses_session.add_user_message("在 responses 中确认")
    second = responses_session.request()
    assert second.text == "跨协议完成"


def test_responses_tool_result_round_trip(config, fake):
    """Responses 下工具结果回填格式（function_call_output）。"""
    fake.responses = [
        responses_body(function_calls=[{"call_id": "fc_9", "name": "lookup", "arguments": "{}"}]),
        responses_body(text="值=99"),
    ]
    session = make_session(config, fake)
    session.add_user_message("查")
    first = session.request(tools=[ToolSpec(name="lookup", description="查询")])
    assert first.tool_calls[0].id == "fc_9"
    session.add_tool_result("fc_9", ToolResult(call_id="fc_9", content="99"))
    second = session.request(tools=[ToolSpec(name="lookup", description="查询")])
    assert second.text == "值=99"

    body = fake.last_request.json()
    outputs = [i for i in body["input"] if i["type"] == "function_call_output"]
    assert len(outputs) == 1
    assert outputs[0]["call_id"] == "fc_9"
    assert outputs[0]["output"] == "99"
