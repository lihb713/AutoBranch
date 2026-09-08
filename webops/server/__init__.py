"""WebOps 行为树管理系统后端（M9b）。

FastAPI 服务：行为树文档 CRUD、清晰度校验（复用 M2）、执行触发与状态查询
（内嵌 M7 引擎）、报告/截图存储与 HTTP 提供。模块 spec 见
``docs/specs/M9b-management-backend.md``。
"""

from webops.server.main import app, create_app

__all__ = ["create_app", "app"]
