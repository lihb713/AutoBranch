"""M10 调度规则模型。

``schedule_rules`` 保存自动触发行为树的配置；实际执行仍由 M8 ``RunService``
负责。``dependencies`` / ``inputs`` 使用 JSON 列，``last_run_at`` 记录“调度触发
时间”（不是执行完成时间），供错过检测与下次时间计算。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from autobranch.server.db import Base
from autobranch.server.models.mixins import TimestampMixin

SCHEDULE_MODES = ("interval", "cron")
INTERVAL_UNITS = ("seconds", "minutes", "hours", "days")
CRON_PERIODS = ("hour", "day", "week")
ON_FAILURE = ("immediate", "next_schedule")
ON_MISSED = ("run", "skip")


class ScheduleRule(Base, TimestampMixin):
    """一条自动调度规则。"""

    __tablename__ = "schedule_rules"
    __table_args__ = (
        CheckConstraint(
            "schedule_mode IN ('interval','cron')", name="ck_schedule_rules_mode"
        ),
        CheckConstraint(
            "on_failure IN ('immediate','next_schedule')",
            name="ck_schedule_rules_on_failure",
        ),
        CheckConstraint(
            "on_missed IN ('run','skip')", name="ck_schedule_rules_on_missed"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_tree_id: Mapped[int] = mapped_column(
        ForeignKey("trees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    schedule_mode: Mapped[str] = mapped_column(String(16), nullable=False)

    interval: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interval_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)

    cron_period: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cron_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cron_weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)

    dependencies: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)

    on_failure: Mapped[str] = mapped_column(
        String(16), nullable=False, default="immediate", server_default="immediate"
    )
    max_retries: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    retry_interval: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default="60"
    )
    on_missed: Mapped[str] = mapped_column(
        String(16), nullable=False, default="run", server_default="run"
    )

    inputs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )


__all__ = [
    "ScheduleRule",
    "SCHEDULE_MODES",
    "INTERVAL_UNITS",
    "CRON_PERIODS",
    "ON_FAILURE",
    "ON_MISSED",
]
