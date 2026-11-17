"""M10 调度时间计算单元测试。"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from autobranch.scheduler.timecalc import (
    calculate_next_run,
    normalize_cron_time,
    to_seconds,
)


def test_interval_next_run() -> None:
    rule = SimpleNamespace(schedule_mode="interval", interval=30, interval_unit="minutes")
    assert calculate_next_run(rule, datetime(2026, 1, 1, 10, 0)) == datetime(
        2026, 1, 1, 10, 30
    )


def test_cron_hour() -> None:
    rule = SimpleNamespace(
        schedule_mode="cron", cron_period="hour", cron_time=":30"
    )
    assert calculate_next_run(rule, datetime(2026, 1, 1, 10, 30)) == datetime(
        2026, 1, 1, 11, 30
    )
    assert calculate_next_run(rule, datetime(2026, 1, 1, 10, 20)) == datetime(
        2026, 1, 1, 10, 30
    )


def test_cron_day() -> None:
    rule = SimpleNamespace(schedule_mode="cron", cron_period="day", cron_time="21:00")
    assert calculate_next_run(rule, datetime(2026, 1, 1, 20, 0)) == datetime(
        2026, 1, 1, 21, 0
    )
    assert calculate_next_run(rule, datetime(2026, 1, 1, 21, 0)) == datetime(
        2026, 1, 2, 21, 0
    )


def test_cron_week_uses_sunday_zero_mapping() -> None:
    # 2026-01-05 是周一；配置 1=周一。
    rule = SimpleNamespace(
        schedule_mode="cron",
        cron_period="week",
        cron_time="07:00",
        cron_weekday=1,
    )
    assert calculate_next_run(rule, datetime(2026, 1, 5, 7, 0)) == datetime(
        2026, 1, 12, 7, 0
    )
    # 配置 0=周日 → Python weekday 6。
    sunday = SimpleNamespace(
        schedule_mode="cron",
        cron_period="week",
        cron_time="07:00",
        cron_weekday=0,
    )
    assert calculate_next_run(sunday, datetime(2026, 1, 5, 7, 0)) == datetime(
        2026, 1, 11, 7, 0
    )


def test_normalize_and_units() -> None:
    assert normalize_cron_time("hour", "30") == ":30"
    assert normalize_cron_time("hour", "09:05") == ":05"
    assert normalize_cron_time("day", "9:05") == "09:05"
    assert to_seconds(2, "hours") == 7200
    with pytest.raises(ValueError):
        normalize_cron_time("day", ":30")
    with pytest.raises(ValueError):
        to_seconds(0, "minutes")
