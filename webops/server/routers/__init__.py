"""M9b HTTP 路由（按资源组织，api-conventions.md §2.1）。"""

from webops.server.routers.reports import router as reports_router
from webops.server.routers.runs import router as runs_router
from webops.server.routers.trees import router as trees_router

__all__ = ["trees_router", "runs_router", "reports_router"]
