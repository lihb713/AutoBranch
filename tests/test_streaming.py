"""任务 7.3：流式请求（可选能力）。"""

from __future__ import annotations

import pytest

from webops.llm.errors import LLMProtocolError
from webops.llm.protocols import parse_chat_stream
from webops.llm.session import LLMSession


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
