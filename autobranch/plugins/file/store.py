"""文件管理平台共享访问层（供 SSH / 浏览器插件联动）。

平台文件存于 ``autobranch/plugins/file/data/``，元数据在服务端 SQLite。
插件在运行期通过本模块读写平台文件；若服务端 DB 未初始化（纯 CLI 场景），
返回清晰错误。
"""

from __future__ import annotations

import os
from contextlib import contextmanager

from .service import FileService, normalize_path, path_join, path_name

SERVICE: FileService | None = None


class FilePlatformError(RuntimeError):
    """文件管理平台不可用或路径非法。"""


def storage_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "data")


def get_service() -> FileService:
    global SERVICE
    if SERVICE is None:
        path = storage_dir()
        os.makedirs(path, exist_ok=True)
        SERVICE = FileService(path)
    return SERVICE


@contextmanager
def session_scope():
    try:
        from autobranch.server.db import session_factory

        factory = session_factory()
    except RuntimeError as exc:
        raise FilePlatformError("文件管理平台未初始化（服务端数据库不可用）") from exc
    db = factory()
    try:
        yield db
    finally:
        db.close()


def read_platform_file(path: str) -> tuple[str, bytes]:
    """按平台路径读取文件，返回 ``(filename, bytes)``。"""
    service = get_service()
    with session_scope() as db:
        result = service.download_file_by_path(db, path)
    if result is None:
        raise FileNotFoundError(f"文件管理平台文件不存在: {path}")
    return result


def write_platform_file(
    path: str,
    content: bytes,
    content_type: str = "application/octet-stream",
    *,
    filename: str | None = None,
) -> dict:
    """把字节写入文件管理平台；返回文件记录。"""
    service = get_service()
    target = normalize_path(path)
    if not target:
        target = normalize_path(filename or "unnamed")
    with session_scope() as db:
        return service.store_file(
            db,
            target,
            content,
            content_type=content_type,
            overwrite=True,
        )


def resolve_download_path(remote_name: str, target: str | None) -> str:
    """目录目标（空/以 / 结尾）自动拼接远程文件名。"""
    raw = str(target or "").replace("\\", "/")
    if not raw or raw.endswith("/"):
        return path_join(raw, path_name(remote_name))
    return normalize_path(raw)


__all__ = [
    "FilePlatformError",
    "get_service",
    "session_scope",
    "read_platform_file",
    "write_platform_file",
    "resolve_download_path",
]
