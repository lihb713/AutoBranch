"""任务 1.2/1.3/1.4：传输层接口、默认实现与 FakeTransport。"""

from __future__ import annotations

import pytest
from fake_transport import FakeTransport

from webops.llm.errors import LLMConnectionError, LLMTimeoutError
from webops.llm.transport import TransportResponse, UrllibTransport


def test_transport_interface_satisfied_by_both():
    """1.2 接口签名可被 fake 与真实实现共同满足。"""
    assert isinstance(FakeTransport(), object)
    assert isinstance(UrllibTransport(), object)


def test_urllib_transport_posts_to_url():
    """1.3 对任意 base_url 发起 POST 并返回状态码与响应体。"""
    transport = UrllibTransport()
    resp = transport.request(
        "https://httpbin.org/post",
        {"Content-Type": "application/json"},
        b'{"hello":"world"}',
        timeout=5,
    )
    assert isinstance(resp, TransportResponse)
    assert resp.status == 200
    assert b"world" in resp.body


def test_urllib_transport_connection_error():
    """DNS 解析失败 / 连接不可达 → LLMConnectionError。"""
    transport = UrllibTransport()
    with pytest.raises(LLMConnectionError):
        transport.request(
            "http://webops-nonexistent-host.invalid/x",
            {"Content-Type": "application/json"},
            b"{}",
            timeout=1,
        )


def test_urllib_transport_timeout():
    """请求挂起 → LLMTimeoutError。"""
    transport = UrllibTransport()
    with pytest.raises(LLMTimeoutError):
        transport.request(
            "http://10.255.255.1/x", {"Content-Type": "application/json"}, b"{}", timeout=0.1
        )


def test_fake_transport_returns_prescribed_sequence():
    """1.4 FakeTransport 拦截请求、返回预设响应序列。"""
    fake = FakeTransport(
        responses=[
            (200, '{"choices":[{"message":{"content":"one"}}]}'),
            (200, '{"choices":[{"message":{"content":"two"}}]}'),
        ]
    )
    first = fake.request("u", {}, b"{}", 1.0)
    second = fake.request("u", {}, b"{}", 1.0)
    assert first.status == 200 and b"one" in first.body
    assert second.status == 200 and b"two" in second.body
    assert len(fake.requests) == 2


def test_fake_transport_records_request_body():
    fake = FakeTransport(responses=[(200, "{}")])
    fake.request("https://api.example/x", {"Authorization": "Bearer k"}, b'{"model":"m"}', 1.0)
    assert fake.last_request is not None
    assert fake.last_request.url == "https://api.example/x"
    assert fake.last_request.headers["Authorization"] == "Bearer k"
    assert fake.last_request.json()["model"] == "m"


def test_fake_transport_exhaustion_raises_connection_error():
    fake = FakeTransport()  # 无预设响应
    with pytest.raises(LLMConnectionError):
        fake.request("u", {}, b"{}", 1.0)
