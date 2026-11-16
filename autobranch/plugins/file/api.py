"""文件插件 REST API：文件列表 / 上传 / 详情 / 下载 / 删除。"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from autobranch.server.db import get_db

from .service import FileService

DbSession = Annotated[Session, Depends(get_db)]


def create_file_router(service: FileService) -> APIRouter:
    router = APIRouter()

    @router.get("/files")
    def list_files(db: DbSession):
        return service.list_files(db)

    @router.post("/files")
    async def upload_file(file: UploadFile, db: DbSession):
        content = await file.read()
        try:
            return service.upload_file(
                db,
                file.filename or "unnamed",
                content,
                file.content_type or "",
            )
        except ValueError as exc:
            raise HTTPException(413, str(exc)) from exc

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
