"""HTTP 接口（M1 spec §5.3、契约 §5.8.2 两种形态）。

- 形态A（``HttpRecorder``）：订阅页面 response 事件，把请求记录进会话级内存
  列表；``clear`` 截断记录；``get_response(method, url_pattern)`` 按 method
  精确匹配 + URL 模式匹配返回首个匹配项（设计决策 D5）。读取只对清理后
  新发生的请求生效，无匹配返回 None 而非错误。
- 形态B（``http_request``）：独立 HTTP 客户端（requests）发起不经页面的请求，
  认证信息由调用方显式提供、不自动附加页面会话 cookie（设计决策 D6）。
"""

from __future__ import annotations

import re
from collections.abc import Callable

import requests

from autobranch.plugins.browser.driver.models import ErrorCode, HttpResponse, OpResult


def url_matches(pattern: str, url: str) -> bool:
    """URL 模式匹配（设计决策 D5）。

    - 不含 ``*``：按子串匹配（``url`` 包含 ``pattern``）。
    - 含 ``*``：``*`` 视为通配符，按全串正则匹配。
    """
    if "*" not in pattern:
        return pattern in url
    regex = re.escape(pattern).replace(r"\*", ".*")
    return re.search(regex, url) is not None


class HttpRecorder:
    """形态A：页面请求监听记录器。

    由 ``BrowserDriver`` 在 context 上订阅 response 事件并调用
    ``record_response``；读取语义见契约 §5.8.2 形态A。

    ``pump`` 为可选的事件泵取回调（由驱动注入）：Playwright sync API 的
    事件只在主线程阻塞于某个 API 调用期间派发，``get_response``/``clear``
    前先短暂阻塞以派发 pending 的 response 事件，保证读取记录是及时的。
    """

    def __init__(self) -> None:
        self._records: list[HttpResponse] = []
        self.pump: Callable[[], None] | None = None

    def clear(self) -> None:
        """清空全部记录，此后读取只对清理后新发生的请求生效。"""
        if self.pump is not None:
            self.pump()
        self._records.clear()

    def get_response(self, method: str, url_pattern: str) -> HttpResponse | None:
        """按 method（大小写不敏感精确匹配）+ URL 模式返回首个匹配响应。

        无匹配时返回 None（非错误，契约 §5.8.2 形态A 场景「无匹配记录」）。
        """
        if self.pump is not None:
            self.pump()
        upper = method.upper()
        for record in self._records:
            if record.method.upper() == upper and url_matches(url_pattern, record.url):
                return record
        return None

    def record_response(self, response: object) -> None:
        """订阅入口：把一次 Playwright response 追加进记录表。"""
        try:
            body = response.body().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        self._records.append(
            HttpResponse(
                method=str(response.request.method).upper(),
                url=str(response.url),
                status=int(response.status),
                headers={k: v for k, v in (response.headers or {}).items()},
                body=body,
            )
        )


def http_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    timeout_ms: int | None = None,
) -> OpResult:
    """形态B：发起不经页面的独立 HTTP 请求。

    认证信息由调用方在 ``headers`` 显式提供；请求不带任何页面会话 cookie。
    传输层失败（连接失败/超时等）返回 ``ok=False`` + 分类错误码（程序侧可重试）；
    收到 HTTP 状态码即视为成功返回（状态码由调用方在响应中读取）。
    """
    if not isinstance(method, str) or not method.strip():
        return OpResult(False, "method 非法", {"code": ErrorCode.INVALID_ARGUMENT})
    if not isinstance(url, str) or not url:
        return OpResult(False, "url 为空", {"code": ErrorCode.INVALID_ARGUMENT})

    timeout = (timeout_ms or 30000) / 1000.0
    try:
        resp = requests.request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            data=body,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return OpResult(
            False,
            f"独立请求失败: {exc}",
            {"code": ErrorCode.NETWORK, "method": method.upper(), "url": url},
        )

    response = HttpResponse(
        method=method.upper(),
        url=resp.url,
        status=resp.status_code,
        headers=dict(resp.headers),
        body=resp.text,
    )
    return OpResult(True, detail={"response": response})
