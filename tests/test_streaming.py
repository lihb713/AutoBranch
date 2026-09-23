"""任务 7.3：流式请求（可选能力）+ 流式响应解析/自动兼容。"""

from __future__ import annotations

import pytest
from fake_transport import chat_response, responses_body

from autobranch.llm.errors import LLMProtocolError
from autobranch.llm.protocols import ChatCompletionsAdapter, parse_chat_stream
from autobranch.llm.session import LLMSession


def make_sse_stream(parts: list[str]) -> bytes:
    """构造 Chat Completions SSE 流。"""
    lines = []
    for p in parts:
        lines.append(f'data: {{"choices":[{{"delta":{{"content":"{p}"}}}}]}}')
    lines.append("data: [DONE]")
    return "\n\n".join(lines).encode("utf-8")


def test_parse_chat_stream_chunks():
    body = make_sse_stream(["你好", "，", "世界"])
    chunks = parse_chat_stream(body)
    assert chunks == ["你好", "，", "世界"]


def test_stream_chunks_aggregate_consistently(config, fake):
    """分段返回内容与最终汇聚结果一致。"""
    fake.responses = [make_sse_stream(["这是", "一段", "流式", "回复"])]
    session = LLMSession(config=config, system_prompt="s", transport=fake)
    session.add_user_message("hi")
    chunks = session.stream()
    assert chunks == ["这是", "一段", "流式", "回复"]
    assert "".join(chunks) == "这是一段流式回复"


def test_stream_sets_stream_flag(config, fake):
    fake.responses = [make_sse_stream(["ok"])]
    session = LLMSession(config=config, system_prompt="s", transport=fake)
    session.add_user_message("hi")
    session.stream()
    assert fake.last_request.json()["stream"] is True


def test_stream_responses_protocol_raises(config, fake):
    fake.responses = [b""]
    session = LLMSession(config=config, system_prompt="s", transport=fake, protocol="responses")
    session.add_user_message("hi")
    with pytest.raises(LLMProtocolError):
        session.stream()


# ------------------------------------------------------------- 流式响应解析（任务 1.1）

def make_stream(*events: dict) -> bytes:
    lines = []
    for e in events:
        lines.append(f"data: {__import__('json').dumps(e, ensure_ascii=False)}")
    lines.append("data: [DONE]")
    return "\n\n".join(lines).encode("utf-8")


def test_parse_stream_response_content():
    body = make_stream(
        {"choices": [{"delta": {"content": "你好"}}]},
        {"choices": [{"delta": {"content": "世界"}}]},
    )
    resp, usage = ChatCompletionsAdapter().parse_stream_response(body)
    assert resp.text == "你好世界"
    assert resp.tool_calls == []
    assert usage is None


def test_parse_stream_response_tool_calls_accumulate():
    body = make_stream(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "id": "call_1", "type": "function",
                             "function": {"name": "click", "arguments": '{"ref":'}}
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 0, "function": {"arguments": " 1}"}}]}}
            ]
        },
    )
    resp, _ = ChatCompletionsAdapter().parse_stream_response(body)
    assert resp.text == ""
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].id == "call_1"
    assert resp.tool_calls[0].name == "click"
    assert resp.tool_calls[0].arguments == '{"ref": 1}'


def test_parse_stream_response_usage_from_final_chunk():
    body = make_stream(
        {"choices": [{"delta": {"content": "ok"}}]},
        {"choices": [{"delta": {}}], "usage": {"prompt_tokens": 5, "completion_tokens": 3}},
    )
    resp, usage = ChatCompletionsAdapter().parse_stream_response(body)
    assert resp.text == "ok"
    assert usage == {"prompt_tokens": 5, "completion_tokens": 3}


def test_parse_stream_response_invalid_arguments_raises():
    body = make_stream(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "c",
                                "function": {"name": "click", "arguments": "not-json"},
                            }
                        ]
                    }
                }
            ]
        }
    )
    with pytest.raises(LLMProtocolError):
        ChatCompletionsAdapter().parse_stream_response(body)


# ------------------------------------------------------------- 请求路径流式/回落/缓存（任务 2）

def test_request_default_streams_and_parses_sse(config, fake):
    fake.responses = [make_stream({"choices": [{"delta": {"content": "流式"}}]})]
    session = LLMSession(config=config, system_prompt="s", transport=fake)
    session.add_user_message("hi")
    resp = session.request()
    assert fake.last_request.json()["stream"] is True
    assert resp.text == "流式"


def test_request_shape_detects_full_json_when_stream_ignored(config, fake):
    """端点接受 stream=true 但忽略并返回完整 JSON → 按 JSON 解析。"""
    fake.responses = [chat_response(text="完整")]
    session = LLMSession(config=config, system_prompt="s", transport=fake)
    session.add_user_message("hi")
    resp = session.request()
    assert fake.last_request.json()["stream"] is True
    assert resp.text == "完整"


def test_request_fallback_when_stream_rejected_and_cache(config, fake):
    """端点拒绝流式（400+含 stream）→ 回落非流式成功 → 按端点缓存非流式。"""
    fake.responses = [
        (400, '{"error":{"message":"stream is not supported"}}'),
        chat_response(text="非流式结果"),
    ]
    session = LLMSession(config=config, system_prompt="s", transport=fake)
    session.add_user_message("hi")
    resp = session.request()
    assert resp.text == "非流式结果"
    assert fake.requests[0].json()["stream"] is True
    assert fake.requests[1].json()["stream"] is False

    # 同一端点（同 base_url）新会话：缓存命中，直接非流式，不再回落
    fake.responses = [chat_response(text="再跑")]
    session2 = LLMSession(config=config, system_prompt="s", transport=fake)
    session2.add_user_message("hi")
    session2.request()
    assert fake.requests[-1].json()["stream"] is False


def test_request_responses_protocol_non_streaming(config, fake):
    fake.responses = [responses_body(text="ok")]
    session = LLMSession(config=config, system_prompt="s", transport=fake, protocol="responses")
    session.add_user_message("hi")
    resp = session.request()
    assert fake.last_request.json()["stream"] is False
    assert resp.text == "ok"
