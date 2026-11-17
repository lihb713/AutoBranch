"""M10 调度规则 API schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ScheduleRuleCreate(BaseModel):
    """创建/更新调度规则（PUT 为全量更新）。"""

    name: str = Field(min_length=1, max_length=128)
    target_tree_id: int
    schedule_mode: Literal["interval", "cron"]
    interval: int | None = Field(default=None, ge=1)
    interval_unit: Literal["seconds", "minutes", "hours", "days"] | None = None
    cron_period: Literal["hour", "day", "week"] | None = None
    cron_time: str | None = None
    cron_weekday: int | None = Field(default=None, ge=0, le=6)
    dependencies: list[int] = Field(default_factory=list)
    on_failure: Literal["immediate", "next_schedule"] = "immediate"
    max_retries: int = Field(default=3, ge=0, le=20)
    retry_interval: int = Field(default=60, ge=1)
    on_missed: Literal["run", "skip"] = "run"
    inputs: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ScheduleRuleOut(BaseModel):
    id: int
    name: str
    target_tree_id: int
    target_tree_name: str = ""
    schedule_mode: str
    interval: int | None = None
    interval_unit: str | None = None
    cron_period: str | None = None
    cron_time: str | None = None
    cron_weekday: int | None = None
    dependencies: list[int] = Field(default_factory=list)
    on_failure: str
    max_retries: int
    retry_interval: int
    on_missed: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    last_run_at: datetime | None = None
    last_run_id: int | None = None
    last_status: str | None = None
    last_error: str | None = None
    next_run_at: datetime | None = None
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ScheduleRunNowOut(BaseModel):
    run_id: int


__all__ = ["ScheduleRuleCreate", "ScheduleRuleOut", "ScheduleRunNowOut"]
