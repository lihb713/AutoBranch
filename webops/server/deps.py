"""FastAPI 共享依赖（从 ``app.state`` 取服务单例）。

服务在 ``create_app`` 中装配（真实/测试注入），路由与类依赖经这些 getter
解耦，避免模块级全局单例。类型注解仅作契约提示（``TYPE_CHECKING`` 防止
与服务层形成循环导入）。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Request

from webops.server.config import ServerConfig

if TYPE_CHECKING:
    from webops.server.services.engine import EngineService
    from webops.server.services.reports import ReportService
    from webops.server.services.runs import RunService


def get_settings(request: Request) -> ServerConfig:
    return request.app.state.settings


def get_report_root(request: Request) -> Path:
    return request.app.state.settings.report_root


def get_engine_service(request: Request) -> EngineService:
    return request.app.state.engine_service


def get_report_service(request: Request) -> ReportService:
    return request.app.state.report_service


def get_run_service(request: Request) -> RunService:
    return request.app.state.run_service


__all__ = [
    "get_settings",
    "get_report_root",
    "get_engine_service",
    "get_report_service",
    "get_run_service",
]
