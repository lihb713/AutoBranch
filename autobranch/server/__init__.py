"""AutoBranch 行为树管理系统后端（M9b）。

FastAPI 服务：行为树文档 CRUD、清晰度校验（复用 M2）、执行触发与状态查询
（内嵌 M7 引擎）、报告/截图存储与 HTTP 提供。模块 spec 见
``docs/specs/M9b-management-backend.md``。

采用延迟导入，避免插件 ``models.py`` 导入 ``autobranch.server.db`` 时触发
``autobranch.server.main`` 的循环导入。
"""

from __future__ import annotations

__all__ = ["create_app", "app"]


def __getattr__(name: str):
    if name in ("app", "create_app"):
        from autobranch.server.main import app, create_app

        return create_app if name == "create_app" else app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
