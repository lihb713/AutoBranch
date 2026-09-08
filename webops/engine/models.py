"""引擎函数层数据契约（M5 spec §5.2/§5.5，复用 M1/M0 既有类型）。

- ``OpResult`` / ``FatalBrowserError``：复用 M1 浏览器驱动定义——M5 的函数
  统一返回 ``OpResult``，普通失败以工具结果回传 LLM，致命错误（浏览器崩溃）
  抛出 ``FatalBrowserError``（契约 §5.8/§9.4）。
- ``ToolSpec``：复用 M0 LLM 客户端的工具定义结构（name/description/
  parameters JSON Schema），供 ``ENGINE_TOOLS`` 注册表使用。
- ``success`` / ``failure``：引擎函数成功/失败结果便捷构造器（M5 spec §5.5）。
"""

from __future__ import annotations

from typing import Any

from webops.browser import ErrorCode, FatalBrowserError, OpResult
from webops.llm import ToolSpec


def success(detail: dict[str, Any] | None = None) -> OpResult:
    """构造成功结果（可携带操作产物 detail）。"""
    return OpResult(True, detail=detail)


def failure(error: str, code: str = ErrorCode.UNKNOWN, **extra: Any) -> OpResult:
    """构造失败结果：可读错误信息 + 分类错误码（契约 §9.4）。"""
    detail: dict[str, Any] = {"code": code}
    detail.update(extra)
    return OpResult(False, error, detail)


__all__ = [
    "OpResult",
    "FatalBrowserError",
    "ToolSpec",
    "ErrorCode",
    "success",
    "failure",
]
