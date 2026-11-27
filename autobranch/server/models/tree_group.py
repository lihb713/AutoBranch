"""行为树分组模型（树管理分组）。"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from autobranch.server.db import Base
from autobranch.server.models.mixins import TimestampMixin


class TreeGroup(Base, TimestampMixin):
    """行为树分组；默认分组由数据库初始化保证存在且不可删除。"""

    __tablename__ = "tree_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )


__all__ = ["TreeGroup"]
