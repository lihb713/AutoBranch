"""M9b HTTP 路由（按资源组织，api-conventions.md §2.1）。"""

from autobranch.server.routers.functions import router as functions_router
from autobranch.server.routers.plugins import router as plugins_router
from autobranch.server.routers.reports import router as reports_router
from autobranch.server.routers.runs import router as runs_router
from autobranch.server.routers.trees import router as trees_router
from autobranch.server.routers.types import router as types_router

__all__ = [
    "trees_router",
    "runs_router",
    "reports_router",
    "plugins_router",
    "functions_router",
    "types_router",
]
