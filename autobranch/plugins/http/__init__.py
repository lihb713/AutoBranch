"""独立 HTTP 能力插件：不经页面的 HTTP 请求（认证由 headers 显式提供）。"""

from __future__ import annotations

from autobranch.plugin_system import FunctionResult, PluginBase, engine_function
from autobranch.plugins.browser.driver.http import http_request as _http_request


def _props(required: tuple[str, ...], **props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(required)}


class HttpPlugin(PluginBase):
    """独立 HTTP 请求能力（requests 风格单一入口）。"""

    name = "http"
    description = "HTTP 能力：独立发起请求（不经页面；认证经 headers 显式提供）"

    @engine_function(
        name="request",
        description=(
            "发起 HTTP 请求并返回响应（类似 requests.request：method/url 必填，"
            "headers/params/body/json/timeout 可选；返回 status/body/headers；"
            "不经页面，认证经 headers 显式提供）"
        ),
        parameters=_props(
            ("method", "url"),
            method={"type": "string", "description": "HTTP 方法，如 GET/POST"},
            url={"type": "string", "description": "请求 URL"},
            headers={"type": "object", "description": "请求头"},
            params={"type": "object", "description": "URL 查询参数"},
            body={"type": "string", "description": "原始请求体（表单/文本）"},
            json={"type": "object", "description": "JSON 请求体"},
            timeout={"type": "number", "description": "超时秒数（默认 30）"},
        ),
        returns={"status": "int", "body": "str", "headers": "object"},
    )
    def request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        params: dict | None = None,
        body: str | None = None,
        json: dict | None = None,
        timeout: float | None = None,
    ) -> FunctionResult:
        result = _http_request(
            method,
            url,
            headers=headers,
            params=params,
            body=body,
            json=json,
            timeout=timeout,
        )
        if not result.ok:
            return FunctionResult.failure(
                result.error or "HTTP 请求失败", **dict(result.detail or {})
            )
        response = result.detail["response"]
        return FunctionResult.success(
            response.status,
            response.body,
            response.headers,
            response=response,
        )


plugin = HttpPlugin()

__all__ = ["HttpPlugin", "plugin"]
