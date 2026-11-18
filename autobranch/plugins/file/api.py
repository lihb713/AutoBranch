"""文件插件 REST API：目录/文件列表、上传、下载、目录 CRUD。"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from autobranch.server.db import get_db

from .service import FileConflictError, FileService, FileTooLargeError

DbSession = Annotated[Session, Depends(get_db)]


class DirectoryIn(BaseModel):
    path: str


def _raise(exc: Exception) -> None:
    if isinstance(exc, FileConflictError):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, FileTooLargeError):
        raise HTTPException(413, str(exc)) from exc
    raise HTTPException(400, str(exc)) from exc


def create_file_router(service: FileService) -> APIRouter:
    router = APIRouter()

    @router.get("/files")
    def list_files(db: DbSession):
        return service.list_files(db)

    @router.get("/entries")
    def list_entries(db: DbSession, path: str = ""):
        try:
            return service.list_entries(db, path)
        except Exception as exc:  # noqa: BLE001
            _raise(exc)

    @router.get("/directories")
    def list_directories(db: DbSession):
        return service.list_directories(db)

    @router.post("/directories")
    def create_directory(payload: DirectoryIn, db: DbSession):
        try:
            return service.create_directory(db, payload.path)
        except Exception as exc:  # noqa: BLE001
            _raise(exc)

    @router.put("/directories/{dir_id}")
    def rename_directory(dir_id: int, payload: DirectoryIn, db: DbSession):
        try:
            return service.rename_directory(db, dir_id, payload.path)
        except Exception as exc:  # noqa: BLE001
            _raise(exc)

    @router.delete("/directories/{dir_id}")
    def delete_directory(dir_id: int, db: DbSession, recursive: bool = True):
        try:
            if not service.delete_directory(db, dir_id, recursive=recursive):
                raise HTTPException(404, "目录不存在")
            return {"ok": True}
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            _raise(exc)

    @router.post("/files")
    async def upload_file(
        file: UploadFile,
        db: DbSession,
        path: str = Form(""),
    ):
        content = await file.read()
        try:
            return service.upload_file(
                db,
                file.filename or "unnamed",
                content,
                file.content_type or "",
                path=path,
            )
        except Exception as exc:  # noqa: BLE001
            _raise(exc)

    @router.get("/download")
    def download_path(path: str, db: DbSession):
        try:
            result = service.download_path(db, path)
        except Exception as exc:  # noqa: BLE001
            _raise(exc)
        if result is None:
            raise HTTPException(404, "文件/目录不存在")
        filename, content, media_type = result
        disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": disposition},
        )

    @router.get("/files/{file_id}")
    def get_file(file_id: int, db: DbSession):
        result = service.get_file(db, file_id)
        if result is None:
            raise HTTPException(404, "文件不存在")
        return result

    @router.get("/files/{file_id}/download")
    def download_file(file_id: int, db: DbSession):
        result = service.download_file(db, file_id)
        if result is None:
            raise HTTPException(404, "文件不存在")
        filename, content = result
        disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": disposition},
        )

    @router.delete("/files/{file_id}")
    def delete_file(file_id: int, db: DbSession):
        if not service.delete_file(db, file_id):
            raise HTTPException(404, "文件不存在")
        return {"ok": True}

    return router


__all__ = ["create_file_router"]
