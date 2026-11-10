"""行为树文档模型（database-rules.md §2.3）。

``name`` 唯一（业务重名 409 由唯一约束兜底），``content`` 为 yaml 文本。
``status`` 区分草稿/正式版：同一棵行为树只有一份文档，编辑正式版即转为草稿。
"""

from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from autobranch.server.db import Base
from autobranch.server.models.mixins import TimestampMixin

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"


class Tree(Base, TimestampMixin):
    """行为树文档库（单文档 + 草稿/正式状态）。"""

    __tablename__ = "trees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=STATUS_PUBLISHED, server_default=STATUS_PUBLISHED
    )


__all__ = ["Tree", "STATUS_DRAFT", "STATUS_PUBLISHED"]
