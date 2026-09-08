"""执行相关路由：状态轮询 / 执行报告 / 回溯报告。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from webops.server.db import get_db
from webops.server.deps import get_run_service
from webops.server.schemas.run import ExecStateOut
from webops.server.services.runs import RunService

router = APIRouter(prefix="/api/runs", tags=["runs"])

RunServiceDep = Annotated[RunService, Depends(get_run_service)]
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/{run_id}/state", response_model=ExecStateOut)
def get_run_state(run_id: int, run_service: RunServiceDep, db: DbSession):
    """轮询执行状态（契约 §12.4，前端每秒轮询）。"""
    return run_service.get_state(db, run_id)


@router.get("/{run_id}/report")
def get_run_report(run_id: int, run_service: RunServiceDep, db: DbSession):
    """执行报告：进行中返回状态标识，结束返回报告文本（text/markdown）。"""
    result = run_service.get_report(db, run_id)
    if isinstance(result, dict):
        return result
    return PlainTextResponse(result, media_type="text/markdown; charset=utf-8")


@router.get("/{run_id}/trace")
def get_run_trace(run_id: int, run_service: RunServiceDep, db: DbSession):
    """回溯报告：进行中返回状态标识，结束返回报告文本（text/markdown）。"""
    result = run_service.get_trace(db, run_id)
    if isinstance(result, dict):
        return result
    return PlainTextResponse(result, media_type="text/markdown; charset=utf-8")


__all__ = ["router"]
