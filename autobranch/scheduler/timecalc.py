"""M10 调度时间计算。

只支持两类轻量调度：
- ``interval``：固定间隔（秒/分/时/天）；
- ``cron``：每小时第 N 分钟 / 每天 HH:MM / 每周某天 HH:MM。

统一使用服务端本地时间（naive datetime），不引入第三方 cron 依赖。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

_UNIT_SECONDS = {
    "seconds": 1,
    "minutes": 60,
    "hours": 3600,
    "days": 86400,
}

_HH_MM = re.compile(r"^(\d{1,2}):(\d{2})$")
_HOUR_MINUTE = re.compile(r"^:(\d{1,2})$")
_MINUTE_ONLY = re.compile(r"^(\d{1,2})$")


def to_seconds(interval: int, unit: str) -> int:
    """间隔数值 + 单位 → 秒。"""
    multiplier = _UNIT_SECONDS.get(unit)
    if multiplier is None:
        raise ValueError(f"不支持的间隔单位: {unit}")
    if interval <= 0:
        raise ValueError("间隔必须大于 0")
    return interval * multiplier


def normalize_cron_time(period: str, text: str) -> str:
    """校验并归一化 cron 时间。

    - ``hour``：``":30"`` / ``"30"`` / ``"09:30"`` → ``":30"``；
    - ``day`` / ``week``：``"HH:MM"``（24 小时制）。
    """
    raw = (text or "").strip()
    if period == "hour":
        minute_match = _HOUR_MINUTE.match(raw) or _MINUTE_ONLY.match(raw)
        if minute_match:
            minute = int(minute_match.group(1))
            if 0 <= minute <= 59:
                return f":{minute:02d}"
        hhmm = _HH_MM.match(raw)
        if hhmm is None:
            raise ValueError("每小时调度时间格式应为 :MM（如 :30）")
        hour, minute = int(hhmm.group(1)), int(hhmm.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("时间超出范围")
        return f":{minute:02d}"

    hhmm = _HH_MM.match(raw)
    if hhmm is None:
        raise ValueError("定时时间格式应为 HH:MM（如 21:00）")
    hour, minute = int(hhmm.group(1)), int(hhmm.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("时间超出范围")
    return f"{hour:02d}:{minute:02d}"


def parse_cron_time(period: str, text: str | None) -> tuple[int, int]:
    """解析归一化后的 cron 时间，返回 ``(hour, minute)``。hour 模式 hour 恒为 0。"""
    normalized = normalize_cron_time(period, text or "")
    if normalized.startswith(":"):
        return 0, int(normalized[1:])
    hour_text, minute_text = normalized.split(":", 1)
    return int(hour_text), int(minute_text)


def calculate_next_run(rule: Any, last_run_at: datetime) -> datetime | None:
    """根据规则与上次触发时间计算下一次应触发时间。"""
    mode = getattr(rule, "schedule_mode", None)
    if mode == "interval":
        interval = getattr(rule, "interval", None)
        unit = getattr(rule, "interval_unit", None)
        if interval is None or unit is None:
            return None
        try:
            seconds = to_seconds(int(interval), str(unit))
        except ValueError:
            return None
        return last_run_at + timedelta(seconds=seconds)

    if mode == "cron":
        period = getattr(rule, "cron_period", None)
        if period not in ("hour", "day", "week"):
            return None
        try:
            hour, minute = parse_cron_time(str(period), getattr(rule, "cron_time", None))
        except ValueError:
            return None

        if period == "hour":
            next_run = last_run_at.replace(minute=minute, second=0, microsecond=0)
            if next_run <= last_run_at:
                next_run += timedelta(hours=1)
            return next_run

        if period == "day":
            next_run = last_run_at.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            if next_run <= last_run_at:
                next_run += timedelta(days=1)
            return next_run

        weekday = getattr(rule, "cron_weekday", None)
        if weekday is None or not 0 <= int(weekday) <= 6:
            return None
        # Python weekday: 周一=0 ... 周日=6；配置: 0=周日, 1=周一 ... 6=周六。
        target = (int(weekday) - 1) % 7
        days_ahead = (target - last_run_at.weekday()) % 7
        next_run = (last_run_at + timedelta(days=days_ahead)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if next_run <= last_run_at:
            next_run += timedelta(days=7)
        return next_run

    return None


__all__ = [
    "calculate_next_run",
    "normalize_cron_time",
    "parse_cron_time",
    "to_seconds",
]
