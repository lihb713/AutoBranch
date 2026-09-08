"""测试用 FakeTransport：拦截请求、返回预设响应序列（任务 1.4）。

实现 ``webops.llm.transport.Transport`` 接口，可被协议/会话/预算逻辑
离线测试共用。记录所有发出的请求，供断言请求体格式。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from webops.llm.errors import LLMConnectionError
from webops.llm.transport import Transport, TransportResponse


@dataclass
class RecordedRequest:
    url: str
    headers: dict[str, str]
    body: bytes

    def json(self) -> dict:
        return json.loads(self.body.decode("utf-8"))


class FakeTransport(Transport):
    """预设响应序列的传输桩。

    :param responses: 依次返回的响应序列（字节或 str，或带状态码的元组）。
        耗尽后再请求将抛出 :class:`LLMConnectionError`。
    :param error: 若设置，每次请求都抛出该异常（模拟连接失败）。
    :param hanging: 若设置，请求将挂起直到超时（模拟超时）。
    """

    def __init__(
        self,
        responses: list[TransportResponse | bytes | str | tuple[int, str]] | None = None,
        error: Exception | None = None,
        hanging: bool = False,
    ) -> None:
        self._queue: list[TransportResponse] = []
        self.error = error
        self.hanging = hanging
        self.requests: list[RecordedRequest] = []
        self.responses = responses or []

    @property
    def responses(self) -> list[TransportResponse]:
        return list(self._queue)

    @responses.setter
    def responses(self, value: list[TransportResponse | bytes | str | tuple[int, str]]) -> None:
        self._queue = [_coerce(item) for item in value]

    def request(
        self, url: str, headers: dict[str, str], body: bytes, timeout: float
    ) -> TransportResponse:
        self.requests.append(RecordedRequest(url=url, headers=headers, body=body))
        if self.error is not None:
            raise self.error
        if self.hanging:
            import time

            time.sleep(timeout + 10)
        if not self._queue:
            raise LLMConnectionError("FakeTransport: 预设响应已耗尽")
        return self._queue.pop(0)

    @property
    def last_request(self) -> RecordedRequest | None:
        return self.requests[-1] if self.requests else None


def _coerce(item: TransportResponse | bytes | str | tuple[int, str]) -> TransportResponse:
    if isinstance(item, TransportResponse):
        return item
    if isinstance(item, tuple):
        status, body = item
        return TransportResponse(status=status, body=body.encode("utf-8"))
    if isinstance(item, bytes):
        return TransportResponse(status=200, body=item)
    return TransportResponse(status=200, body=item.encode("utf-8"))


def chat_response(
    text: str = "",
    tool_calls: list[dict] | None = None,
    usage: dict | None = None,
) -> bytes:
    """构造一个 Chat Completions 响应体。"""
    message: dict = {"role": "assistant", "content": text}
    if tool_calls:
        message["tool_calls"] = tool_calls
    payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
    }
    if usage:
        payload["usage"] = usage
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def responses_body(
    text: str = "",
    function_calls: list[dict] | None = None,
    usage: dict | None = None,
) -> bytes:
    """构造一个 Responses 响应体。"""
    output: list[dict] = []
    if text:
        output.append(
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        )
    for fc in function_calls or []:
        output.append({"type": "function_call", **fc})
    payload = {"id": "resp-test", "object": "response", "output": output}
    if usage:
        payload["usage"] = usage
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")
