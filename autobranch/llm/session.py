"""agent 式 LLM 会话（契约 §5.7.2）。

会话以 system 提示词初始化，可添加用户消息、声明可调用工具；模型回复
包含工具调用请求时，调用方执行工具并以工具结果回填后再次请求，如此循环。
会话持有完整消息序列，每次 ``request`` 全量携带（设计决策 D4）。

错误分类（设计决策 D6 / 契约 §9.4）：
- 网络/连接异常 → ``LLMConnectionError``（传输层抛出）
- HTTP 401/403 → ``LLMAuthError``
- 请求超时 → ``LLMTimeoutError``（传输层抛出）
- 累计 token 超预算 → ``LLMBudgetExceeded``
"""

from __future__ import annotations

import json
import threading
import time
import uuid

from autobranch.llm.config import LLMConfig
from autobranch.llm.errors import (
    LLMAuthError,
    LLMConnectionError,
    LLMProtocolError,
    LLMTimeoutError,
)
from autobranch.llm.models import LLMResponse, Message, ToolResult, ToolSpec
from autobranch.llm.protocols import ADAPTERS, ProtocolName, parse_chat_stream
from autobranch.llm.token import TokenAccount, TokenBudget, account_from_usage, estimate_tokens
from autobranch.llm.transport import Transport, TransportResponse, UrllibTransport, encode_json

DEFAULT_TIMEOUT = 60.0

#: HTTP 瞬时失败状态码（连接层偶发，重试可恢复）：429 限流 / 5xx 服务端。
_TRANSIENT_STATUS = (429, 500, 502, 503, 504)

#: 流式被拒信号状态码（请求形态不被端点支持）。
_MODE_REJECT_STATUS = (400, 405, 422, 501)

#: 端点 → 已工作请求形态缓存（进程级：base_url+端点后缀 → 是否流式）。
#: 避免"仅支持非流式"端点每次请求都触发一次"拒绝 → 回落"。
_STREAM_MODE_CACHE: dict[str, bool] = {}
_STREAM_MODE_LOCK = threading.Lock()


class _TransientError(Exception):
    """内部标记：HTTP 瞬时失败（触发重试，不终止叶子）。"""

    def __init__(self, status: int) -> None:
        super().__init__(f"LLM 服务瞬时错误 (HTTP {status})")
        self.status = status


class _StreamModeRejected(Exception):
    """内部标记：端点拒绝当前请求形态（流式/非流式），应切换形态重试。"""


class LLMSession:
    """多轮工具调用会话。

    :param config: LLM 配置（base_url / api_key / model）。
    :param system_prompt: system 提示词。
    :param transport: 传输实现（默认 ``UrllibTransport``，测试注入 fake）。
    :param protocol: 协议形态（``chat`` / ``responses``）。
    :param budget_limit: token 预算上限（None 表示不检测）。
    :param timeout: 单次请求超时秒数。
    :param session_id: 可选，覆盖会话标识（``x-opencode-session``）；缺省用
        ``config.session_id``，仍未提供则自动生成 UUID。同一会话内多次请求
        共用同一 ID（供网关路由与提示缓存优化）。
    """

    def __init__(
        self,
        config: LLMConfig,
        system_prompt: str,
        transport: Transport | None = None,
        protocol: ProtocolName = "chat",
        budget_limit: int | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        session_id: str | None = None,
    ) -> None:
        self.config = config
        self.system_prompt = system_prompt
        self.transport = transport or UrllibTransport()
        self.protocol = protocol
        self._adapter = ADAPTERS[protocol]
        self._timeout = timeout
        self._budget = TokenBudget(budget_limit)
        self._messages: list[Message] = []
        self._session_id = session_id or config.session_id or f"autobranch-{uuid.uuid4()}"
        self._url = self._build_url()

    def _build_url(self) -> str:
        base = self.config.base_url.rstrip("/")
        return f"{base}{self._adapter.endpoint_suffix}"

    # ---- 会话构建 ----

    def add_user_message(self, content: str) -> None:
        self._messages.append(Message(role="user", content=content))

    def add_tool_result(self, call_id: str, result: ToolResult | str) -> None:
        content = result.content if isinstance(result, ToolResult) else result
        self._messages.append(Message(role="tool", content=content, tool_call_id=call_id))

    def add_assistant_turn(self, response: LLMResponse) -> None:
        """记录模型回复为会话上下文（内部使用，供协议切换保持一致性）。"""
        self._messages.append(
            Message(role="assistant", content=response.text, tool_calls=response.tool_calls or None)
        )

    # ---- 请求 ----

    def request(
        self, tools: list[ToolSpec] | None = None, stream: bool | None = None
    ) -> LLMResponse:
        """携带会话内全量消息序列发起一次请求（对瞬时失败自动重试）。

        请求形态（流式/非流式）自动兼容：
        - ``stream=None``（默认）：chat 协议**默认流式**，端点拒绝时自动回落非流式，
          并按端点缓存已工作形态；responses 协议恒非流式。
        - ``stream=True/False``：强制指定形态（不触发自动回落）。

        :raises LLMConnectionError: 网络连接失败（传输层抛出）。
        :raises LLMAuthError: 鉴权失败（401/403）。
        :raises LLMTimeoutError: 请求超时（传输层抛出）。
        :raises LLMBudgetExceeded: 累计 token 超过预算上限。
        :raises LLMProtocolError: 响应无法解析。

        对连接错误/超时/HTTP 429/5xx 按 ``config.retry_times`` 指数退避重试；
        成功才累积上下文，故重试不会重复消息。
        """
        mode = self._resolve_mode(stream)
        try:
            return self._request_with_retries(tools, mode)
        except _StreamModeRejected:
            other = not mode
            with _STREAM_MODE_LOCK:
                _STREAM_MODE_CACHE[self._url] = other
            return self._request_with_retries(tools, other)

    def _resolve_mode(self, stream: bool | None) -> bool:
        """确定请求形态：显式指定优先；否则 chat 默认流式（按端点缓存），responses 恒非流式。"""
        if stream is not None:
            return stream
        if self.protocol != "chat":
            return False
        with _STREAM_MODE_LOCK:
            return _STREAM_MODE_CACHE.get(self._url, True)

    def _request_with_retries(self, tools: list[ToolSpec] | None, mode: bool) -> LLMResponse:
        attempts = self.config.retry_times + 1
        for attempt in range(attempts):
            try:
                return self._request_once(tools, mode)
            except (LLMConnectionError, LLMTimeoutError, _TransientError) as exc:
                if attempt >= self.config.retry_times:
                    if isinstance(exc, _TransientError):
                        raise LLMProtocolError(
                            f"LLM 服务瞬时错误持续（HTTP {exc.status}）"
                        ) from exc
                    raise
                time.sleep(self.config.retry_delay * (2**attempt))
        raise LLMProtocolError("LLM 请求重试耗尽")  # 理论不可达

    def _request_once(
        self, tools: list[ToolSpec] | None, mode: bool
    ) -> LLMResponse:
        payload = self._adapter.build_request(
            model=self.config.model,
            system_prompt=self.system_prompt,
            messages=self._messages,
            tools=tools,
            stream=mode,
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.config.auth_header_value(),
            "x-opencode-session": self._session_id,
        }
        resp = self.transport.request(self._url, headers, encode_json(payload), self._timeout)
        if resp.status in _TRANSIENT_STATUS:
            raise _TransientError(resp.status)
        self._check_http_status(resp)
        if resp.status in _MODE_REJECT_STATUS and b"stream" in resp.body.lower():
            raise _StreamModeRejected
        llm_response, usage = self._parse_by_shape(resp.body, mode)
        self._accumulate_tokens(usage, payload, llm_response)
        # 记录模型回复为上下文：tool 消息必须紧跟对应 assistant tool_calls 消息，
        # 且多轮循环要求上下文持续累积（契约 §5.7.2）。
        self.add_assistant_turn(llm_response)
        self._budget.check_and_raise()
        return llm_response

    def _parse_by_shape(self, body: bytes, mode: bool) -> tuple[LLMResponse, dict]:
        """按响应体形态解析：SSE 流式（``data:`` 前缀）走流式解析，否则按完整 JSON 解析。

        兼容"端点接受 stream=true 但忽略并返回完整 JSON"的场景。
        """
        if mode and body.lstrip().startswith(b"data:"):
            return self._adapter.parse_stream_response(body)
        return self._adapter.parse_response(body)

    def _check_http_status(self, resp: TransportResponse) -> None:
        if resp.status in (401, 403):
            raise LLMAuthError(f"LLM 鉴权失败 (HTTP {resp.status})")

    def stream(self, tools: list[ToolSpec] | None = None) -> list[str]:
        """流式请求（可选能力）：分段返回内容，最终汇聚。

        当前传输为同步阻塞式，返回完整 body；本方法按 SSE 事件切分内容
        分段返回，并返回分段列表。汇聚结果 = ``"".join(分段)``。
        仅支持 Chat Completions 流（``parse_chat_stream``）。
        """
        if self.protocol != "chat":
            raise LLMProtocolError("流式请求当前仅支持 Chat Completions 协议")
        payload = self._adapter.build_request(
            model=self.config.model,
            system_prompt=self.system_prompt,
            messages=self._messages,
            tools=tools,
            stream=True,
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.config.auth_header_value(),
            "x-opencode-session": self._session_id,
        }
        resp = self.transport.request(self._url, headers, encode_json(payload), self._timeout)
        self._check_http_status(resp)
        chunks = parse_chat_stream(resp.body)
        self._budget.add(
            TokenAccount(tokens=estimate_tokens("".join(chunks)), source="estimated")
        )
        self._budget.check_and_raise()
        return chunks

    def _accumulate_tokens(
        self, usage: dict | None, payload: dict, llm_response: LLMResponse
    ) -> None:
        account = account_from_usage(usage)
        if account.tokens == 0:
            text = json.dumps(payload, ensure_ascii=False) + llm_response.text
            account = TokenAccount(tokens=estimate_tokens(text), source="estimated")
        self._budget.add(account)

    # ---- token 查询 ----

    def token_used(self) -> int:
        """会话累计 token（只增不减）。"""
        return self._budget.total

    def exceeds_budget(self, limit: int) -> bool:
        """判断累计 token 是否超过给定预算上限。"""
        return self._budget.exceeds(limit)

    @property
    def budget_limit(self) -> int | None:
        return self._budget.limit

    @property
    def message_count(self) -> int:
        return len(self._messages)
