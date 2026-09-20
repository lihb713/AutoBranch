"""执行相关路由：实例列表 / 状态轮询 / 执行报告 / 回溯报告 / 重试 / 删除。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from autobranch.server.db import get_db
from autobranch.server.deps import get_run_service
from autobranch.server.schemas.run import (
    ExecStateOut,
    RunDetailOut,
    RunOut,
    RunStartOut,
)
from autobranch.server.services.runs import RunService

router = APIRouter(prefix="/api/runs", tags=["runs"])

RunServiceDep = Annotated[RunService, Depends(get_run_service)]
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[RunOut])
def list_runs(run_service: RunServiceDep, db: DbSession):
    """执行实例列表（created_at 倒序）：状态/快照树名/入参/耗时/指纹/进度。"""
    return [RunOut.model_validate(item) for item in run_service.list_runs(db)]


@router.get("/{run_id}", response_model=RunDetailOut)
def get_run_detail(run_id: int, run_service: RunServiceDep, db: DbSession):
    """执行实例详情（含快照内容，供查看快照/重试）。"""
    return RunDetailOut.model_validate(run_service.get_detail(db, run_id))


@router.post("/{run_id}/retry", response_model=RunStartOut, status_code=status.HTTP_202_ACCEPTED)
def retry_run(run_id: int, run_service: RunServiceDep, db: DbSession):
    """按快照重试：复制原实例的树内容快照 + 入参新建执行实例。"""
    run = run_service.retry(db, run_id)
    return {"run_id": run.id}


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run(run_id: int, run_service: RunServiceDep, db: DbSession):
    """删除执行实例（连带清理其报告目录）。"""
    run_service.delete(db, run_id)


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
