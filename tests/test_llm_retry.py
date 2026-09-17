"""LLM 请求瞬时失败重试测试（session 层）。"""

from __future__ import annotations

import pytest
from fake_transport import chat_response

from autobranch.llm import LLMConfig, LLMSession
from autobranch.llm.errors import LLMConnectionError, LLMProtocolError
from autobranch.llm.transport import TransportResponse


class _FlakyTransport:
    """前 n 次抛连接错误，之后返回正常响应。"""

    def __init__(self, fail_before: int, response: bytes) -> None:
        self.fail_before = fail_before
        self.response = response
        self.count = 0

    def request(self, url, headers, body, timeout):
        self.count += 1
        if self.count <= self.fail_before:
            raise LLMConnectionError("临时连接故障")
        return TransportResponse(status=200, body=self.response)


class _AlwaysFailTransport:
    def request(self, url, headers, body, timeout):
        raise LLMConnectionError("持续故障")


class _Flaky429Transport:
    """前 n 次返回 HTTP 429，之后返回 200。"""

    def __init__(self, fail_before: int, response: bytes) -> None:
        self.fail_before = fail_before
        self.response = response
        self.count = 0

    def request(self, url, headers, body, timeout):
        self.count += 1
        if self.count <= self.fail_before:
            return TransportResponse(status=429, body=b"{}")
        return TransportResponse(status=200, body=self.response)


def _session(transport, retry_times=2):
    config = LLMConfig(
        base_url="http://x",
        api_key="k",
        model="m",
        retry_times=retry_times,
        retry_delay=0.01,
    )
    session = LLMSession(config=config, system_prompt="s", transport=transport)
    session.add_user_message("hi")
    return session


def test_retries_on_connection_error():
    transport = _FlakyTransport(fail_before=2, response=chat_response(text="OK"))
    resp = _session(transport).request()
    assert resp.text == "OK"
    assert transport.count == 3


def test_retry_exhausted_raises_connection_error():
    with pytest.raises(LLMConnectionError):
        _session(_AlwaysFailTransport(), retry_times=2).request()


def test_retries_on_http_429():
    transport = _Flaky429Transport(fail_before=2, response=chat_response(text="OK"))
    resp = _session(transport).request()
    assert resp.text == "OK"
    assert transport.count == 3


def test_http_429_persistent_raises_protocol_error():
    transport = _Flaky429Transport(fail_before=99, response=b"{}")
    with pytest.raises(LLMProtocolError):
        _session(transport, retry_times=1).request()
