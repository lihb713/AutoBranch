"""文件插件业务逻辑：目录/文件管理（插件函数与 REST API 共用）。

存储根为插件目录 ``data/``；数据库存 POSIX 风格相对路径（如
``reports/2026/a.txt``）。上传统一使用路径表达；目录记录单独存表。
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import zipfile

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import FileDirectory, FileRecord


class FileTooLargeError(ValueError):
    """文件超过配置大小上限。"""


class FileConflictError(FileExistsError):
    """路径已存在。"""


def normalize_path(path: str | None) -> str:
    """归一化 POSIX 相对路径；拒绝 ``..`` 与空段。"""
    text = str(path or "").replace("\\", "/").strip()
    parts: list[str] = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("路径不允许包含 ..")
        parts.append(part)
    return "/".join(parts)


def path_parent(path: str) -> str:
    text = normalize_path(path)
    return text.rsplit("/", 1)[0] if "/" in text else ""


def path_name(path: str) -> str:
    text = normalize_path(path)
    return text.rsplit("/", 1)[-1] if text else ""


def path_join(base: str, name: str) -> str:
    base_text = normalize_path(base)
    name_text = normalize_path(name)
    if not base_text:
        return name_text
    if not name_text:
        return base_text
    return f"{base_text}/{name_text}"


class FileService:
    """文件管理服务；文件与目录统一存放在插件目录 ``data/`` 下。"""

    def __init__(self, storage_dir: str, max_file_size: int = 10 * 1024 * 1024) -> None:
        self._storage_dir = storage_dir
        self.max_file_size = max_file_size
        self._ensure_dir()

    @property
    def storage_root(self) -> str:
        return os.path.abspath(self._storage_dir)

    def _ensure_dir(self) -> None:
        os.makedirs(self._storage_dir, exist_ok=True)

    def _full_path(self, path: str) -> str:
        normalized = normalize_path(path)
        base = os.path.abspath(self._storage_dir)
        full = os.path.abspath(os.path.join(base, *normalized.split("/"))) if normalized else base
        if full != base and not full.startswith(base + os.sep):
            raise ValueError("非法文件路径")
        return full

    # ------------------------------------------------------------- 目录

    def list_entries(self, db: Session, path: str = "") -> dict:
        directory = normalize_path(path)
        files = db.scalars(select(FileRecord).order_by(FileRecord.path)).all()
        dirs = db.scalars(select(FileDirectory).order_by(FileDirectory.path)).all()
        return {
            "path": directory,
            "directories": [
                self._dir_to_dict(item)
                for item in dirs
                if path_parent(item.path) == directory
            ],
            "files": [
                self._to_dict(item)
                for item in files
                if path_parent(item.path) == directory
            ],
        }

    def list_directories(self, db: Session) -> list[dict]:
        rows = db.scalars(select(FileDirectory).order_by(FileDirectory.path)).all()
        return [self._dir_to_dict(item) for item in rows]

    def get_directory(self, db: Session, dir_id: int) -> dict | None:
        record = db.get(FileDirectory, dir_id)
        return self._dir_to_dict(record) if record is not None else None

    def get_directory_by_path(self, db: Session, path: str) -> dict | None:
        record = self._dir_by_path(db, normalize_path(path))
        return self._dir_to_dict(record) if record is not None else None

    def create_directory(self, db: Session, path: str) -> dict:
        directory = normalize_path(path)
        if not directory:
            raise ValueError("目录路径不能为空")
        if self._file_by_path(db, directory) is not None:
            raise FileConflictError(f"同名文件已存在: {directory}")
        existing = self._dir_by_path(db, directory)
        if existing is not None:
            return self._dir_to_dict(existing)
        self._ensure_parent_dirs(db, directory)
        os.makedirs(self._full_path(directory), exist_ok=True)
        record = FileDirectory(path=directory)
        db.add(record)
        db.commit()
        db.refresh(record)
        return self._dir_to_dict(record)

    def rename_directory(self, db: Session, dir_id: int, new_path: str) -> dict:
        record = db.get(FileDirectory, dir_id)
        if record is None:
            raise FileNotFoundError("目录不存在")
        old = normalize_path(record.path)
        new = normalize_path(new_path)
        if not new:
            raise ValueError("新目录路径不能为空")
        if new == old:
            return self._dir_to_dict(record)
        if new.startswith(old + "/"):
            raise ValueError("不能把目录移动到自身子目录")
        if self._file_by_path(db, new) is not None or self._dir_by_path(db, new) is not None:
            raise FileConflictError(f"目标路径已存在: {new}")
        self._ensure_parent_dirs(db, new)
        old_full = self._full_path(old)
        new_full = self._full_path(new)
        if os.path.exists(new_full):
            raise FileConflictError(f"目标路径已存在: {new}")
        if os.path.isdir(old_full):
            os.makedirs(os.path.dirname(new_full), exist_ok=True)
            os.rename(old_full, new_full)
        for item in db.scalars(select(FileDirectory)).all():
            if item.path == old or item.path.startswith(old + "/"):
                item.path = new + item.path[len(old) :]
        for item in db.scalars(select(FileRecord)).all():
            if item.path.startswith(old + "/"):
                item.path = new + item.path[len(old) :]
        db.commit()
        db.refresh(record)
        return self._dir_to_dict(record)

    def delete_directory(self, db: Session, dir_id: int, *, recursive: bool = True) -> bool:
        record = db.get(FileDirectory, dir_id)
        if record is None:
            return False
        path = normalize_path(record.path)
        files = [
            item
            for item in db.scalars(select(FileRecord)).all()
            if item.path.startswith(path + "/")
        ]
        children = [
            item
            for item in db.scalars(select(FileDirectory)).all()
            if item.path.startswith(path + "/")
        ]
        if not recursive and (files or children):
            raise ValueError("目录非空，请使用递归删除")
        for item in files:
            db.delete(item)
        for item in children:
            db.delete(item)
        db.delete(record)
        shutil.rmtree(self._full_path(path), ignore_errors=True)
        db.commit()
        return True

    # ------------------------------------------------------------- 文件

    def list_files(self, db: Session) -> list[dict]:
        rows = db.scalars(select(FileRecord).order_by(FileRecord.created_at.desc())).all()
        return [self._to_dict(r) for r in rows]

    def list_files_under(self, db: Session, path: str = "") -> list[dict]:
        """递归列出目录下文件（不读取内容），返回 path/relative。"""
        directory = normalize_path(path)
        prefix = f"{directory}/" if directory else ""
        rows = db.scalars(select(FileRecord).order_by(FileRecord.path)).all()
        return [
            {"path": record.path, "relative": record.path[len(prefix) :]}
            for record in rows
            if record.path.startswith(prefix)
        ]

    def upload_file(
        self,
        db: Session,
        filename: str,
        content: bytes,
        content_type: str = "",
        path: str | None = None,
    ) -> dict:
        safe_name = os.path.basename(filename or "unnamed") or "unnamed"
        raw_path = str(path or "").replace("\\", "/")
        target = normalize_path(raw_path or safe_name)
        if not target:
            target = safe_name
        dir_target = raw_path.endswith("/") or self._is_directory(db, target)
        if dir_target:
            target = path_join(target, safe_name)
        return self.store_file(
            db,
            target,
            content,
            content_type=content_type or "application/octet-stream",
            overwrite=False,
        )

    def store_file(
        self,
        db: Session,
        path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        *,
        overwrite: bool = True,
    ) -> dict:
        target = normalize_path(path)
        if not target:
            raise ValueError("文件路径不能为空")
        if len(content) > self.max_file_size:
            raise FileTooLargeError(f"文件过大（>{self.max_file_size} 字节）")
        existing = self._file_by_path(db, target)
        if existing is not None and not overwrite:
            raise FileConflictError(f"文件已存在: {target}")
        if existing is None and self._dir_by_path(db, target) is not None:
            raise FileConflictError(f"同名目录已存在: {target}")
        self._ensure_parent_dirs(db, target)
        full_path = self._full_path(target)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as handle:
            handle.write(content)
        if existing is None:
            existing = FileRecord(
                filename=path_name(target),
                path=target,
                size=len(content),
                content_type=content_type,
            )
            db.add(existing)
        else:
            existing.filename = path_name(target)
            existing.size = len(content)
            existing.content_type = content_type
        db.commit()
        db.refresh(existing)
        return self._to_dict(existing)

    def md5_by_path(self, db: Session, path: str) -> str | None:
        record = self._file_by_path(db, normalize_path(path))
        if record is None:
            return None
        full_path = self._full_path(record.path)
        if not os.path.isfile(full_path):
            return None
        return self._md5_file(full_path)

    def get_file(self, db: Session, file_id: int) -> dict | None:
        record = db.get(FileRecord, file_id)
        return self._to_dict(record) if record is not None else None

    def get_file_by_path(self, db: Session, path: str) -> dict | None:
        record = self._file_by_path(db, normalize_path(path))
        return self._to_dict(record) if record is not None else None

    def download_file_by_path(
        self, db: Session, path: str
    ) -> tuple[str, bytes] | None:
        record = self._file_by_path(db, normalize_path(path))
        if record is None:
            return None
        full_path = self._full_path(record.path)
        if not os.path.isfile(full_path):
            return None
        with open(full_path, "rb") as handle:
            return record.filename, handle.read()

    def download_file(self, db: Session, file_id: int) -> tuple[str, bytes] | None:
        record = db.get(FileRecord, file_id)
        if record is None:
            return None
        full_path = self._full_path(record.path)
        if not os.path.isfile(full_path):
            return None
        with open(full_path, "rb") as handle:
            return record.filename, handle.read()

    def download_path(self, db: Session, path: str) -> tuple[str, bytes, str] | None:
        """按路径下载文件或目录（目录返回 zip）。"""
        normalized = normalize_path(path)
        record = self._file_by_path(db, normalized)
        if record is not None:
            result = self.download_file_by_path(db, normalized)
            if result is None:
                return None
            return result[0], result[1], record.content_type or "application/octet-stream"
        if not self._is_directory(db, normalized):
            return None
        directory_full = self._full_path(normalized)
        if not os.path.isdir(directory_full):
            return None
        root_name = path_name(normalized) or "files"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            has_content = False
            for current, _dirs, files in os.walk(directory_full):
                rel_dir = os.path.relpath(current, directory_full)
                if rel_dir != ".":
                    archive.write(current, f"{root_name}/{rel_dir}")
                    has_content = True
                for name in files:
                    full = os.path.join(current, name)
                    rel = os.path.relpath(full, directory_full)
                    archive.write(full, f"{root_name}/{rel}")
                    has_content = True
            if not has_content:
                archive.writestr(f"{root_name}/", b"")
        return f"{root_name}.zip", buffer.getvalue(), "application/zip"

    def delete_file(self, db: Session, file_id: int) -> bool:
        record = db.get(FileRecord, file_id)
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

    def delete_file_by_path(self, db: Session, path: str) -> bool:
        record = self._file_by_path(db, normalize_path(path))
        return self.delete_file(db, record.id) if record is not None else False

    # ------------------------------------------------------------- 内部

    def _file_by_path(self, db: Session, path: str) -> FileRecord | None:
        return db.scalars(select(FileRecord).where(FileRecord.path == path)).first()

    def _dir_by_path(self, db: Session, path: str) -> FileDirectory | None:
        return db.scalars(select(FileDirectory).where(FileDirectory.path == path)).first()

    def _is_directory(self, db: Session, path: str) -> bool:
        return self._dir_by_path(db, path) is not None

    def _ensure_parent_dirs(self, db: Session, path: str) -> None:
        parent = path_parent(path)
        if not parent:
            return
        prefix = ""
        for part in parent.split("/"):
            prefix = path_join(prefix, part)
            if self._dir_by_path(db, prefix) is None:
                db.add(FileDirectory(path=prefix))
            os.makedirs(self._full_path(prefix), exist_ok=True)
        db.flush()

    @staticmethod
    def _dir_to_dict(record: FileDirectory) -> dict:
        return {
            "id": record.id,
            "path": record.path,
            "name": path_name(record.path),
            "created_at": record.created_at.isoformat() if record.created_at else "",
            "updated_at": record.updated_at.isoformat() if record.updated_at else "",
        }

    def _to_dict(self, record: FileRecord) -> dict:
        full_path = self._full_path(record.path)
        return {
            "id": record.id,
            "filename": record.filename,
            "path": record.path,
            "size": record.size,
            "content_type": record.content_type,
            "md5": self._md5_file(full_path) if os.path.isfile(full_path) else "",
            "created_at": record.created_at.isoformat() if record.created_at else "",
            "updated_at": record.updated_at.isoformat() if record.updated_at else "",
        }

    @staticmethod
    def _md5_file(path: str) -> str:
        digest = hashlib.md5()  # noqa: S324 - 用于文件指纹展示，不用于安全认证
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


__all__ = [
    "FileService",
    "FileTooLargeError",
    "FileConflictError",
    "normalize_path",
    "path_parent",
    "path_name",
    "path_join",
]
