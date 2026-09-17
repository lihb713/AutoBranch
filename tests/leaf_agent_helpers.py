"""M6 叶子 agent 测试共享辅助（插件模式 mock 注册表 / 慢传输 / 结果构造器）。

与 ``tests/fake_transport.py`` 同模式：位于 tests 根目录，经
``pythonpath=["tests"]`` 以顶层模块导入，供 ``tests/leaf_agent/`` 用例复用。
"""

from __future__ import annotations

import json
import time

from fake_transport import TransportResponse

from autobranch.browser import ErrorCode, OpResult
from autobranch.leaf_agent.models import LeafContext
from autobranch.llm import LLMConfig, LLMConnectionError, LLMSession
from autobranch.llm.transport import Transport
from autobranch.plugin_system import FunctionDef, FunctionResult


class MockRegistry:
    """插件模式 mock 注册表（替代旧 ``StubEngine``）。

    :param results: 函数名 → ``OpResult`` / ``FunctionResult`` / 序列 / 可调用。
    :param raise_next: 下一次调用抛出的异常（致命错误测试用）。
    :param raise_on: 函数名 → 调用该函数时抛出的异常。
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.results: dict[str, object] = {}
        self.raise_next: Exception | None = None
        self.raise_on: dict[str, Exception] = {}
        self._functions: dict[str, FunctionDef] = {}

    def register(
        self, name: str, *, output_param: str | None = None, parameters: dict | None = None
    ) -> None:
        self._functions[name] = FunctionDef(
            name=name,
            parameters=parameters or {"type": "object", "properties": {}},
            output_param=output_param,
        )

    def function(self, name: str) -> FunctionDef | None:
        return self._functions.get(name)

    def owner(self, name: str) -> str:
        return "mock"

    def loaded_functions(self) -> list[FunctionDef]:
        return list(self._functions.values())

    def is_loaded(self, name: str) -> bool:
        return True

    def ensure_loaded(self, name: str, runtime=None):
        return None

    def call(self, name: str, arguments: dict | None = None, *, runtime=None) -> FunctionResult:
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
                op = OpResult(True, detail={})
            else:
                op = handler.pop(0)
        elif callable(handler):
            op = handler(name, args)
        else:
            op = handler
        return _op_to_result(op, self._functions.get(name))


def _op_to_result(op, spec: FunctionDef | None) -> FunctionResult:
    """把旧 ``OpResult`` 结果转为 ``FunctionResult``（产出型提取 detail 的 value）。"""
    if isinstance(op, FunctionResult):
        return op
    detail = dict(op.detail or {})
    if op.ok:
        if spec is not None and spec.output_param:
            value = detail.pop("value", None)
            return FunctionResult.success(value, **detail)
        return FunctionResult.success(**detail) if detail else FunctionResult.success()
    return FunctionResult.failure(op.error or "失败", **detail)


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


def make_ctx(config, fake, registry, **overrides) -> LeafContext:
    """构造 ``LeafContext``（默认注入假会话工厂与插件 mock 注册表）。"""
    return LeafContext(
        config=config,
        registry=registry,
        session_factory=make_session_factory(fake),
        **overrides,
    )


def graph_result(text: str) -> OpResult:
    """语义图成功结果（detail 携带 text，对齐 ``semantic_graph`` 返回）。"""
    return OpResult(True, detail={"text": text, "ref_count": 1})


def tool_call(name: str, arguments: dict) -> dict:
    """构造 Chat Completions 工具调用消息（供 ``chat_response`` 使用）。"""
    return {
        "id": f"call_{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }
