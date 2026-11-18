"""项目时区工具。

约定：
- 数据库时间戳统一存**配置时区的本地 naive 时间**（默认 ``Asia/Shanghai``），
  前端直接展示本地墙钟时间，避免 SQLite UTC 与 Python 本地时间混用。
- 调度 cron 的 ``HH:MM`` 也按该时区解释。
- 切换配置时区只影响之后产生的时间戳/调度；历史记录保留原时区墙钟值。
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Shanghai"

_timezone_name = DEFAULT_TIMEZONE
_timezone = ZoneInfo(DEFAULT_TIMEZONE)


def configure_timezone(name: str | None) -> str:
    """设置项目时区；非法 IANA 名称抛 ``ValueError``。"""
    global _timezone_name, _timezone
    resolved = (name or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        zone = ZoneInfo(resolved)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"无效时区: {resolved}") from exc
    _timezone_name = resolved
    _timezone = zone
    return resolved


def timezone_name() -> str:
    return _timezone_name


def timezone() -> ZoneInfo:
    return _timezone


def now_local_naive() -> datetime:
    """当前配置时区的本地时间（naive，用于数据库字段）。"""
    return datetime.now(_timezone).replace(tzinfo=None)


def utc_naive_to_local_naive(value: datetime) -> datetime:
    """把旧库的 UTC naive 时间转换为配置时区 naive 时间。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(_timezone).replace(tzinfo=None)


__all__ = [
    "DEFAULT_TIMEZONE",
    "configure_timezone",
    "timezone_name",
    "timezone",
    "now_local_naive",
    "utc_naive_to_local_naive",
]
