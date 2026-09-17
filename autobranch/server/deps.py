"""FastAPI 共享依赖（从 ``app.state`` 取服务单例）。

服务在 ``create_app`` 中装配（真实/测试注入），路由与类依赖经这些 getter
解耦，避免模块级全局单例。类型注解仅作契约提示（``TYPE_CHECKING`` 防止
与服务层形成循环导入）。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Request

from autobranch.server.config import ServerConfig

if TYPE_CHECKING:
    from autobranch.plugin_system import PluginRegistry
    from autobranch.server.services.engine import EngineService
    from autobranch.server.services.plugins import PluginService
    from autobranch.server.services.reports import ReportService
    from autobranch.server.services.runs import RunService


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


def get_plugin_registry(request: Request) -> PluginRegistry:
    return request.app.state.plugin_registry


def get_plugins_dir(request: Request) -> str | None:
    return getattr(request.app.state, "plugins_dir", None)


def get_plugin_service(request: Request) -> PluginService:
    return request.app.state.plugin_service


__all__ = [
    "get_settings",
    "get_report_root",
    "get_engine_service",
    "get_report_service",
    "get_run_service",
    "get_plugin_registry",
    "get_plugins_dir",
    "get_plugin_service",
]
