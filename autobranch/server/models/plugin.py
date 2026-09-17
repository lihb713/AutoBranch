"""插件表模型（plugin-management spec：name/kind/description/functions/source）。

- ``kind``：``builtin``（预置，源码在文件系统，``source`` 恒 NULL）|
  ``custom``（自定义，源码存 DB）。
- ``name`` 唯一（预置/自定义全局唯一，自定义不得与预置同名）。
- ``functions``：函数名清单（JSON 数组，启动扫描/重载时刷新）。
"""

from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from autobranch.server.db import Base
from autobranch.server.models.mixins import TimestampMixin

KIND_BUILTIN = "builtin"
KIND_CUSTOM = "custom"


class Plugin(Base, TimestampMixin):
    """插件表（M8 插件管理）。"""

    __tablename__ = "plugins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=KIND_CUSTOM)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    functions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["Plugin", "KIND_BUILTIN", "KIND_CUSTOM"]
