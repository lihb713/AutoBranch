"""文件插件业务逻辑：文件增删改查（插件函数与 REST API 共用）。"""

from __future__ import annotations

import os
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from autobranch.timeutil import now_local_naive

from .models import FileRecord


class FileService:
    """文件管理服务；文件统一存放在插件目录 ``data/`` 下。"""

    def __init__(self, storage_dir: str, max_file_size: int = 10 * 1024 * 1024) -> None:
        self._storage_dir = storage_dir
        self.max_file_size = max_file_size
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        os.makedirs(self._storage_dir, exist_ok=True)

    def _full_path(self, stored_name: str) -> str:
        base = os.path.abspath(self._storage_dir)
        full = os.path.abspath(os.path.join(base, stored_name))
        if not full.startswith(base + os.sep):
            raise ValueError("非法文件路径")
        return full

    def list_files(self, db: Session) -> list[dict]:
        rows = db.scalars(select(FileRecord).order_by(FileRecord.created_at.desc())).all()
        return [self._to_dict(r) for r in rows]

    def upload_file(
        self, db: Session, filename: str, content: bytes, content_type: str = ""
    ) -> dict:
        if len(content) > self.max_file_size:
            raise ValueError(f"文件过大（>{self.max_file_size} 字节）")
        safe_name = os.path.basename(filename or "unnamed") or "unnamed"
        stamp = now_local_naive().strftime("%Y%m%d%H%M%S")
        stored_name = f"{stamp}_{uuid.uuid4().hex[:8]}_{safe_name}"
        path = self._full_path(stored_name)
        with open(path, "wb") as f:
            f.write(content)
        record = FileRecord(
            filename=safe_name,
            path=stored_name,
            size=len(content),
            content_type=content_type or "application/octet-stream",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return self._to_dict(record)

    def get_file(self, db: Session, file_id: int) -> dict | None:
        record = db.scalars(select(FileRecord).where(FileRecord.id == file_id)).first()
        return self._to_dict(record) if record else None

    def download_file(self, db: Session, file_id: int) -> tuple[str, bytes] | None:
        record = db.scalars(select(FileRecord).where(FileRecord.id == file_id)).first()
        if record is None:
            return None
        full_path = self._full_path(record.path)
        if not os.path.isfile(full_path):
            return None
        with open(full_path, "rb") as f:
            return record.filename, f.read()

    def delete_file(self, db: Session, file_id: int) -> bool:
        record = db.scalars(select(FileRecord).where(FileRecord.id == file_id)).first()
        if record is None:
            return False
        try:
            full_path = self._full_path(record.path)
            if os.path.isfile(full_path):
                os.remove(full_path)
        except (OSError, ValueError):
            pass
        db.delete(record)
        db.commit()
        return True

    @staticmethod
    def _to_dict(record: FileRecord) -> dict:
        return {
            "id": record.id,
            "filename": record.filename,
            "path": record.path,
            "size": record.size,
            "content_type": record.content_type,
            "created_at": record.created_at.isoformat() if record.created_at else "",
            "updated_at": record.updated_at.isoformat() if record.updated_at else "",
        }


__all__ = ["FileService"]
