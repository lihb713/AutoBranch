"""报告/截图文件路由（api-conventions.md §7 路径白名单防目录穿越）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from webops.server.deps import get_report_service
from webops.server.errors import AppError
from webops.server.services.reports import ReportService

router = APIRouter(prefix="/api/reports", tags=["reports"])

ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]

#: 报告根内文件的 MIME 映射（``FileResponse`` 默认按扩展名猜测，
#: Windows 下 ``.md`` 无映射，显式指定保证前端可直接渲染）。
_MEDIA_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
}


@router.get("/{path:path}")
def get_report_file(path: str, report_service: ReportServiceDep):
    """提供报告/截图文件：白名单解析（``is_relative_to(REPORT_ROOT)``）+ FileResponse。"""
    target = report_service.resolve(path)
    if not target.is_file():
        raise AppError(404, f"报告文件不存在: {path}")
    return FileResponse(target, media_type=_MEDIA_TYPES.get(target.suffix.lower()))


__all__ = ["router"]
