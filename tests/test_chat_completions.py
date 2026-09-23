"""任务 3.1/3.2/3.3/3.4：Chat Completions 请求构造与响应解析。"""

from __future__ import annotations

import pytest
from fake_transport import chat_response

from autobranch.llm.errors import LLMProtocolError
from autobranch.llm.models import ToolSpec
from autobranch.llm.session import LLMSession


def make_session(config, fake, system="你是助手"):
    return LLMSession(config=config, system_prompt=system, transport=fake)


def test_chat_request_body_structure(config, fake):
    """3.1 请求体字段结构与顺序正确（messages/system/tools/stream）。"""
    fake.responses = [chat_response(text="你好")]
    session = make_session(config, fake)
    session.add_user_message("1+1=?")
    tools = [ToolSpec(name="calc", description="计算", parameters={"type": "object"})]
    session.request(tools=tools)

    body = fake.last_request.json()
    assert body["model"] == config.model
    assert body["stream"] is True  # 默认流式（自动兼容；响应形态自动识别回落）
    # messages: [system, user]
    assert body["messages"][0] == {"role": "system", "content": "你是助手"}
    assert body["messages"][1] == {"role": "user", "content": "1+1=?"}
    # tools
    assert body["tools"][0]["type"] == "function"
    assert body["tools"][0]["function"]["name"] == "calc"
    assert body["tools"][0]["function"]["description"] == "计算"
    assert body["tools"][0]["function"]["parameters"] == {"type": "object"}
    # auth header
    assert fake.last_request.headers["Authorization"] == "Bearer test-secret-key"
    # endpoint
    assert fake.last_request.url == "https://api.test.example/v1/chat/completions"


def test_chat_parse_text_reply(config, fake):
    """3.2 解析纯文本回复。"""
    fake.responses = [chat_response(text="答案是 2")]
    session = make_session(config, fake)
    session.add_user_message("1+1=?")
    resp = session.request()
    assert resp.text == "答案是 2"
    assert not resp.has_tool_calls


def test_chat_parse_tool_call(config, fake):
    """3.2 解析工具调用请求。"""
    fake.responses = [
        chat_response(
            text="",
            tool_calls=[
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "calc", "arguments": '{"expr":"1+1"}'},
                }
            ],
        )
    ]
    session = make_session(config, fake)
    session.add_user_message("计算 1+1")
    resp = session.request(tools=[ToolSpec(name="calc", description="计算")])
    assert resp.has_tool_calls
    assert len(resp.tool_calls) == 1
    call = resp.tool_calls[0]
    assert call.id == "call_abc"
    assert call.name == "calc"
    assert call.arguments == '{"expr":"1+1"}'


def test_chat_empty_response_returns_empty_text(config, fake):
    """3.3 无文本也无工具调用 → 空文本，不视为错误。"""
    fake.responses = [chat_response()]
    session = make_session(config, fake)
    resp = session.request()
    assert resp.text == ""
    assert not resp.has_tool_calls


def test_chat_invalid_tool_arguments_raises(config, fake):
    """3.4 工具调用 arguments 为非法 JSON → LLMProtocolError。"""
    fake.responses = [
        chat_response(
            tool_calls=[
                {
                    "id": "call_x",
                    "type": "function",
                    "function": {"name": "calc", "arguments": "{not-json"},
                }
            ]
        )
    ]
    session = make_session(config, fake)
    session.add_user_message("计算")
    with pytest.raises(LLMProtocolError, match="不是合法 JSON"):
        session.request(tools=[ToolSpec(name="calc", description="计算")])


def test_chat_malformed_response_raises(config, fake):
    fake.responses = [b'{"unexpected": true}']
    session = make_session(config, fake)
    session.add_user_message("hi")
    with pytest.raises(LLMProtocolError, match="choices"):
        session.request()
