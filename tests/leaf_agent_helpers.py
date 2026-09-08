"""M6 叶子 agent 测试共享辅助（假引擎/慢传输/结果构造器）。

与 ``tests/fake_transport.py`` / ``tests/engine_helpers.py`` 同模式：位于
tests 根目录，经 ``pythonpath=["tests"]`` 以顶层模块导入，供
``tests/leaf_agent/`` 用例复用。
"""

from __future__ import annotations

import json
import time

from fake_transport import TransportResponse

from webops.browser import ErrorCode, OpResult
from webops.leaf_agent.models import LeafContext
from webops.llm import LLMConfig, LLMConnectionError, LLMSession
from webops.llm.transport import Transport


class StubEngine:
    """假 M5 引擎：按函数名返回预设 ``OpResult`` 序列，并记录全部调用。

    :param results: 函数名 → ``OpResult`` / ``OpResult`` 序列 / 可调用对象。
    :param raise_next: 下一次调用抛出的异常（致命错误测试用）。
    :param raise_on: 函数名 → 调用该函数时抛出的异常。
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.results: dict[str, object] = {}
        self.raise_next: Exception | None = None
        self.raise_on: dict[str, Exception] = {}

    def call(self, name: str, arguments: dict | None = None) -> OpResult:
        args = dict(arguments or {})
        self.calls.append((name, args))
        if self.raise_next is not None:
            exc = self.raise_next
            self.raise_next = None
            raise exc
        if name in self.raise_on:
            raise self.raise_on[name]
        handler = self.results.get(
            name,
            OpResult(False, f"未知函数: {name}", {"code": ErrorCode.INVALID_ARGUMENT}),
        )
        if isinstance(handler, list):
            if not handler:
                return OpResult(True, detail={})
            return handler.pop(0)
        if callable(handler):
            return handler(name, args)
        return handler


class SlowTransport(Transport):
    """慢响应传输桩：每次请求 sleep 指定时长后返回预设响应（叶子超时测试用）。"""

    def __init__(self, delay: float, responses: list[TransportResponse]) -> None:
        self.delay = delay
        self._queue = [_coerce_response(item) for item in responses]

    def request(self, url, headers, body, timeout) -> TransportResponse:
        time.sleep(self.delay)
        if not self._queue:
            raise LLMConnectionError("SlowTransport: 预设响应已耗尽")
        return self._queue.pop(0)


def _coerce_response(item) -> TransportResponse:
    """把 bytes/str/元组统一转为 ``TransportResponse``（对齐 FakeTransport 行为）。"""
    if isinstance(item, TransportResponse):
        return item
    if isinstance(item, tuple):
        status, body = item
        return TransportResponse(status=status, body=body.encode("utf-8"))
    if isinstance(item, bytes):
        return TransportResponse(status=200, body=item)
    return TransportResponse(status=200, body=item.encode("utf-8"))


def make_session_factory(fake):
    """构造注入指定传输桩的会话工厂（M0 固定响应 LLM 桩）。"""

    def _factory(config: LLMConfig, system_prompt: str) -> LLMSession:
        return LLMSession(config=config, system_prompt=system_prompt, transport=fake)

    return _factory


def make_ctx(config, fake, engine, **overrides) -> LeafContext:
    """构造 ``LeafContext``（默认注入假会话工厂与 M5 引擎桩）。"""
    return LeafContext(
        config=config,
        engine=engine,
        session_factory=make_session_factory(fake),
        **overrides,
    )


def graph_result(text: str) -> OpResult:
    """语义图成功结果（detail 携带 text，对齐 M5 ``semantic_graph`` 返回）。"""
    return OpResult(True, detail={"text": text, "ref_count": 1})


def tool_call(name: str, arguments: dict) -> dict:
    """构造 Chat Completions 工具调用消息（供 ``chat_response`` 使用）。"""
    return {
        "id": f"call_{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }
