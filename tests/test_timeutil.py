"""项目时区工具测试。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from autobranch.timeutil import (
    DEFAULT_TIMEZONE,
    configure_timezone,
    now_local_naive,
    utc_naive_to_local_naive,
)


def test_default_timezone_is_beijing():
    try:
        assert configure_timezone(None) == DEFAULT_TIMEZONE
        assert configure_timezone(DEFAULT_TIMEZONE) == "Asia/Shanghai"
    finally:
        configure_timezone(DEFAULT_TIMEZONE)


def test_utc_to_local_conversion():
    try:
        configure_timezone("Asia/Shanghai")
        assert utc_naive_to_local_naive(datetime(2026, 1, 1, 0, 0)) == datetime(
            2026, 1, 1, 8, 0
        )
    finally:
        configure_timezone(DEFAULT_TIMEZONE)


def test_now_local_naive_is_close_to_beijing_now():
    try:
        configure_timezone("Asia/Shanghai")
        value = now_local_naive()
        expected = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        assert value.tzinfo is None
        assert abs((value - expected).total_seconds()) < 2
    finally:
        configure_timezone(DEFAULT_TIMEZONE)


def test_invalid_timezone_rejected():
    with pytest.raises(ValueError, match="无效时区"):
        configure_timezone("Not/AZone")
    configure_timezone(DEFAULT_TIMEZONE)
