"""审计时间戳混合（database-rules.md §2.2）。

所有业务表必带 ``created_at`` / ``updated_at``，``updated_at`` 由 ORM
``onupdate`` 维护。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


__all__ = ["TimestampMixin"]
