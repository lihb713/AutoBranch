"""传输层抽象（设计决策 D2）。

定义薄传输接口（发起请求 → 返回状态码 + 响应体），默认实现基于标准库
``urllib.request``（零第三方运行时依赖）；测试注入 ``FakeTransport``
返回预设响应，从协议层验证请求体格式、工具回填与异常分类。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


@dataclass
class TransportResponse:
    """传输层返回结果。

    :param status: HTTP 状态码。
    :param body: 响应体字节（协议层负责解析 JSON）。
    """

    status: int
    body: bytes


class Transport(Protocol):
    """传输层接口：发起请求 → 返回状态码 + 响应体。

    可被默认实现（``UrllibTransport``）与测试桩（``FakeTransport``）共同满足。
    """

    def request(
        self,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> TransportResponse: ...


class UrllibTransport:
    """基于标准库 ``urllib.request`` 的默认传输实现。

    网络异常（连接失败/DNS）抛出 :class:`LLMConnectionError`；
    请求超时抛出 :class:`LLMTimeoutError`。
    """

    #: 默认 User-Agent：部分网关/Cloudflare 对 ``Python-urllib`` 默认 UA 会拦截。
    USER_AGENT = "autobranch-llm-client/0.1"

    def request(
        self,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> TransportResponse:
        request_headers = {"User-Agent": self.USER_AGENT, **headers}
        req = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return TransportResponse(status=resp.status, body=resp.read())
        except urllib.error.HTTPError as exc:
            return TransportResponse(status=exc.code, body=exc.read())
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                from autobranch.llm.errors import LLMTimeoutError

                raise LLMTimeoutError(f"LLM 请求超时: {exc}") from exc
            from autobranch.llm.errors import LLMConnectionError

            raise LLMConnectionError(f"LLM 连接失败: {exc}") from exc
        except TimeoutError as exc:
            from autobranch.llm.errors import LLMTimeoutError

            raise LLMTimeoutError(f"LLM 请求超时: {exc}") from exc
        except OSError as exc:
            from autobranch.llm.errors import LLMConnectionError

            raise LLMConnectionError(f"LLM 连接失败: {exc}") from exc


def encode_json(payload: dict) -> bytes:
    """序列化请求体为 UTF-8 字节。"""
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")
