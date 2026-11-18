"""文件插件数据库模型：文件元数据记录（表前缀 plugin_file_）。"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, String

from autobranch.server.db import Base
from autobranch.timeutil import now_local_naive


class FileRecord(Base):
    """文件管理平台的文件元数据。"""

    __tablename__ = "plugin_file_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(256), nullable=False)
    path = Column(String(512), nullable=False, unique=True)
    size = Column(BigInteger, default=0)
    content_type = Column(String(128), default="")
    created_at = Column(DateTime, default=now_local_naive)
    updated_at = Column(DateTime, default=now_local_naive, onupdate=now_local_naive)


__all__ = ["FileRecord"]
