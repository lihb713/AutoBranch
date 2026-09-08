"""业务异常与统一异常处理器（api-conventions.md §5.3）。

- ``AppError``：携带 HTTP 状态码与 detail 的业务异常，路由层抛出、
  ``register_error_handlers`` 统一转为 JSON 响应。
- ``CheckValidationError``：清晰度校验失败（422，detail 为错误清单）。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """业务异常基类：携带 HTTP 状态码与响应 detail。"""

    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class CheckValidationError(AppError):
    """清晰度校验失败（契约 §4.4）：422 + 可读错误清单。"""

    def __init__(self, issues: list[dict[str, Any]]) -> None:
        super().__init__(422, issues)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


__all__ = ["AppError", "CheckValidationError", "register_error_handlers"]
