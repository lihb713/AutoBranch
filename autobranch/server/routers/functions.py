"""函数清单路由（``GET /api/functions``）。

跨插件聚合全部已注册函数（全名 + 结构化定义），供编辑器函数选择器使用。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from autobranch.server.schemas.plugin import FunctionInfo
from autobranch.server.services.plugins import PluginService

router = APIRouter(prefix="/api/functions", tags=["functions"])

PluginServiceDep = Annotated[PluginService, Depends()]


@router.get("", response_model=list[FunctionInfo])
def list_functions(service: PluginServiceDep):
    return service.list_functions()


__all__ = ["router"]
