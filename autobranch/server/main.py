"""FastAPI 应用入口与装配（设计 D1/D2/D3、任务 6.2 重启恢复）。

- ``create_app(settings, engine_service)``：工厂函数——测试可注入临时数据库
  settings 与 mock 引擎服务；生产默认内嵌真实 M7 引擎（``EmbeddedEngineService``）。
- 模块级 ``app = create_app()`` 供 ``uvicorn autobranch.server.main:app``。
- 启动即扫描 running/pending 记录置 failure（interrupted），保证重启后终态可查。
"""

from __future__ import annotations

from fastapi import FastAPI

from autobranch.plugin_system import PluginRegistry
from autobranch.server.config import ServerConfig
from autobranch.server.db import configure_database, session_factory
from autobranch.server.errors import register_error_handlers
from autobranch.server.routers import (
    functions_router,
    plugins_router,
    reports_router,
    runs_router,
    trees_router,
)
from autobranch.server.services.engine import EmbeddedEngineService, EngineService
from autobranch.server.services.plugins import PluginService
from autobranch.server.services.reports import ReportService
from autobranch.server.services.runs import RunService

APP_TITLE = "AutoBranch 行为树管理系统"

#: 预置插件目录（包内 ``autobranch/plugins/``）。
PLUGINS_DIR = "autobranch/plugins"


def create_app(
    settings: ServerConfig | None = None,
    *,
    engine_service: EngineService | None = None,
) -> FastAPI:
    """构建 FastAPI 应用（测试注入临时 settings / mock 引擎，生产走真实内嵌引擎）。"""
    settings = settings or ServerConfig.load()
    configure_database(settings.db_path)
    settings.report_root.mkdir(parents=True, exist_ok=True)

    registry = PluginRegistry()
    if engine_service is None:
        engine_service = EmbeddedEngineService(
            settings.autobranch_config(),
            settings.report_root,
            registry=registry,
            plugins_dir=PLUGINS_DIR,
        )
    report_service = ReportService(settings.report_root)
    run_service = RunService(
        engine_service, settings.report_root, settings.autobranch_config(), registry=registry
    )

    app = FastAPI(title=APP_TITLE, version="0.1.0")
    app.state.settings = settings
    app.state.engine_service = engine_service
    app.state.report_service = report_service
    app.state.run_service = run_service
    app.state.plugin_registry = registry
    app.state.plugins_dir = PLUGINS_DIR

    register_error_handlers(app)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(trees_router)
    app.include_router(runs_router)
    app.include_router(reports_router)
    app.include_router(plugins_router)
    app.include_router(functions_router)

    # 插件初始化：扫描预置插件 → 写/刷新 builtin 记录（只读）
    with session_factory()() as db:
        PluginService(db=db, registry=registry, plugins_dir=PLUGINS_DIR).init_builtins()

    run_service.mark_interrupted()

    return app


app = create_app()


__all__ = ["create_app", "app"]
