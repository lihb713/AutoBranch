"""行为树文档 CRUD 服务（设计 D1：业务逻辑下沉 service 层）。

业务规则：重名 409、不存在 404（抛 ``AppError``）；保存前经 M2 清晰度校验
（``validate_document``，失败 422 不落库，契约 §12.5）；删除行为树时级联
删除其执行记录（FK CASCADE）并清理报告文件。
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webops.server.db import get_db
from webops.server.deps import get_report_root
from webops.server.errors import AppError
from webops.server.models import Run, Tree
from webops.server.schemas.tree import TreeCreate, TreeDetailOut, TreeOut, TreeUpdate
from webops.server.services.validation import validate_document

DbSession = Annotated[Session, Depends(get_db)]
ReportRoot = Annotated[Path, Depends(get_report_root)]


class TreeService:
    """行为树文档库服务（会话经 FastAPI DI 注入）。"""

    def __init__(self, db: DbSession, report_root: ReportRoot) -> None:
        self.db = db
        self.report_root = report_root

    # ------------------------------------------------------------- 查询

    def list_all(self) -> list[TreeOut]:
        trees = self.db.scalars(select(Tree).order_by(Tree.id)).all()
        return [TreeOut.model_validate(tree) for tree in trees]

    def get(self, tree_id: int) -> Tree:
        tree = self.db.get(Tree, tree_id)
        if tree is None:
            raise AppError(404, f"行为树不存在 (id={tree_id})")
        return tree

    def get_detail(self, tree_id: int) -> TreeDetailOut:
        tree = self.get(tree_id)
        return TreeDetailOut.model_validate(tree)

    def get_content(self, tree_id: int) -> Tree:
        return self.get(tree_id)

    def get_by_name(self, name: str) -> Tree:
        """按文档名查（文档名唯一）：供跨文档引用加载 / 前端 ref 展开。"""
        tree = self.db.scalars(select(Tree).where(Tree.name == name)).first()
        if tree is None:
            raise AppError(404, f"行为树不存在 (name={name})")
        return tree

    # ------------------------------------------------------------- 变更

    def create(self, payload: TreeCreate) -> TreeOut:
        validate_document(payload.content, payload.name)
        tree = Tree(name=payload.name, content=payload.content)
        self.db.add(tree)
        self._commit_or_conflict()
        self.db.refresh(tree)
        return TreeOut.model_validate(tree)

    def update(self, tree_id: int, payload: TreeUpdate) -> TreeOut:
        tree = self.get(tree_id)
        new_name = payload.name if payload.name is not None else tree.name
        new_content = payload.content if payload.content is not None else tree.content
        validate_document(new_content, new_name)
        tree.name = new_name
        tree.content = new_content
        self._commit_or_conflict()
        self.db.refresh(tree)
        return TreeOut.model_validate(tree)

    def delete(self, tree_id: int) -> None:
        tree = self.get(tree_id)
        run_ids = [run.id for run in self.db.scalars(select(Run).where(Run.tree_id == tree_id))]
        self.db.delete(tree)
        self.db.commit()
        for run_id in run_ids:
            self._cleanup_run_files(run_id)

    # ------------------------------------------------------------- 内部

    def _commit_or_conflict(self) -> None:
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise AppError(409, "行为树名称已存在") from None

    def _cleanup_run_files(self, run_id: int) -> None:
        target = (self.report_root / str(run_id)).resolve()
        if target.is_relative_to(self.report_root.resolve()):
            import shutil

            shutil.rmtree(target, ignore_errors=True)


__all__ = ["TreeService"]
