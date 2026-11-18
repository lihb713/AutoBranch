"""审计时间戳混合（database-rules.md §2.2）。

所有业务表必带 ``created_at`` / ``updated_at``。时间戳按项目配置时区
（默认 ``Asia/Shanghai``）写入本地 naive 时间，由 ORM 默认值维护。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from autobranch.timeutil import now_local_naive


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local_naive, onupdate=now_local_naive
    )


__all__ = ["TimestampMixin"]
