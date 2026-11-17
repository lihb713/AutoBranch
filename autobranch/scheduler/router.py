"""M10 调度规则 HTTP 路由。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from autobranch.scheduler.engine import SchedulerEngine
from autobranch.scheduler.schemas import (
    ScheduleRuleCreate,
    ScheduleRuleOut,
    ScheduleRunNowOut,
)
from autobranch.scheduler.service import ScheduleService
from autobranch.server.db import get_db
from autobranch.server.deps import get_run_service, get_schedule_engine
from autobranch.server.schemas.run import RunOut
from autobranch.server.services.runs import RunService

router = APIRouter(prefix="/api/schedules", tags=["schedules"])

DbSession = Annotated[Session, Depends(get_db)]
ScheduleEngineDep = Annotated[SchedulerEngine, Depends(get_schedule_engine)]
RunServiceDep = Annotated[RunService, Depends(get_run_service)]


def get_schedule_service(db: DbSession) -> ScheduleService:
    return ScheduleService(db)


ScheduleServiceDep = Annotated[ScheduleService, Depends(get_schedule_service)]


@router.get("", response_model=list[ScheduleRuleOut])
def list_schedules(service: ScheduleServiceDep):
    return service.list_rules()


@router.post("", response_model=ScheduleRuleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(payload: ScheduleRuleCreate, service: ScheduleServiceDep):
    return service.create(payload)


@router.get("/{rule_id}", response_model=ScheduleRuleOut)
def get_schedule(rule_id: int, service: ScheduleServiceDep):
    return service.get_out(rule_id)


@router.put("/{rule_id}", response_model=ScheduleRuleOut)
def update_schedule(
    rule_id: int, payload: ScheduleRuleCreate, service: ScheduleServiceDep
):
    return service.update(rule_id, payload)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(rule_id: int, service: ScheduleServiceDep):
    service.delete(rule_id)


@router.patch("/{rule_id}/toggle", response_model=ScheduleRuleOut)
def toggle_schedule(rule_id: int, service: ScheduleServiceDep):
    return service.toggle(rule_id)


@router.post(
    "/{rule_id}/run",
    response_model=ScheduleRunNowOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_schedule_now(rule_id: int, engine: ScheduleEngineDep):
    """立即执行一次（不检查前置依赖，不影响调度周期）。"""
    return {"run_id": engine.trigger_now(rule_id)}


@router.get("/{rule_id}/runs", response_model=list[RunOut])
def list_schedule_runs(
    rule_id: int, run_service: RunServiceDep, db: DbSession
):
    return [
        RunOut.model_validate(item)
        for item in run_service.list_runs(db, schedule_id=rule_id)
    ]


__all__ = ["router", "get_schedule_service"]
