"""行为树文档模型（database-rules.md §2.3）。

``name`` 唯一（业务重名 409 由唯一约束兜底），``content`` 为 yaml 文本。
"""

from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from webops.server.db import Base
from webops.server.models.mixins import TimestampMixin


class Tree(Base, TimestampMixin):
    """行为树文档库。"""

    __tablename__ = "trees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = ["Tree"]
