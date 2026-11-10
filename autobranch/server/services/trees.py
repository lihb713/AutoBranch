"""行为树文档 CRUD 服务（后端权威文档 + 草稿/正式状态）。

业务规则：
- 新建树为 ``draft``；对正式树的任何编辑立即转为 ``draft``（同一记录）。
- 草稿允许未通过清晰度校验；保存时校验并转 ``published``。
- 删除保留历史执行实例（``Run.tree_id`` SET NULL）。
- 命令式编辑由 :mod:`tree_doc` 应用，默认接收名/类型由 :mod:`normalize` 补全。
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from autobranch.plugin_system import PluginRegistry
from autobranch.server.db import get_db
from autobranch.server.deps import get_plugin_registry
from autobranch.server.errors import AppError
from autobranch.server.models import STATUS_DRAFT, STATUS_PUBLISHED, Tree
from autobranch.server.schemas.tree import (
    TreeCommand,
    TreeCreate,
    TreeDetailOut,
    TreeOut,
    TreeUpdate,
)
from autobranch.server.services import tree_doc
from autobranch.server.services.doclib import DbResolver
from autobranch.server.services.normalize import normalize_tree_content
from autobranch.server.services.validation import validate_document

DbSession = Annotated[Session, Depends(get_db)]
Registry = Annotated[PluginRegistry, Depends(get_plugin_registry)]


class TreeService:
    """行为树文档库服务（会话经 FastAPI DI 注入）。"""

    def __init__(self, db: DbSession, registry: Registry = None) -> None:
        self.db = db
        self.registry = registry

    # ------------------------------------------------------------- 查询

    @staticmethod
    def _declared_inputs(content: str) -> dict[str, str]:
        from autobranch.parser.yamlio import normalize_document

        raw = (normalize_document(content) or {}).get("inputs") or {}
        if not isinstance(raw, dict):
            return {}
        return {str(k): str(v) for k, v in raw.items()}

    def _out(self, tree: Tree) -> TreeOut:
        return TreeOut(
            id=tree.id,
            name=tree.name,
            created_at=tree.created_at,
            updated_at=tree.updated_at,
            status=tree.status,
            inputs=self._declared_inputs(tree.content),
        )

    def list_all(self) -> list[TreeOut]:
        trees = self.db.scalars(select(Tree).order_by(Tree.id)).all()
        return [self._out(tree) for tree in trees]

    def list_published(self) -> list[TreeOut]:
        trees = self.db.scalars(
            select(Tree).where(Tree.status == STATUS_PUBLISHED).order_by(Tree.id)
        ).all()
        return [self._out(tree) for tree in trees]

    def get(self, tree_id: int) -> Tree:
        tree = self.db.get(Tree, tree_id)
        if tree is None:
            raise AppError(404, f"行为树不存在 (id={tree_id})")
        return tree

    def get_detail(self, tree_id: int) -> TreeDetailOut:
        tree = self.get(tree_id)
        out = self._out(tree)
        return TreeDetailOut(
            id=out.id,
            name=out.name,
            created_at=out.created_at,
            updated_at=out.updated_at,
            status=out.status,
            inputs=out.inputs,
            content=tree.content,
        )

    def get_content(self, tree_id: int) -> Tree:
        return self.get(tree_id)

    def get_by_name(self, name: str, *, published_only: bool = True) -> Tree:
        """按文档名查；ref 解析/编辑器目标选择只允许正式版。"""
        stmt = select(Tree).where(Tree.name == name)
        if published_only:
            stmt = stmt.where(Tree.status == STATUS_PUBLISHED)
        tree = self.db.scalars(stmt).first()
        if tree is None:
            hint = "（该行为树尚未保存为正式版）" if published_only else ""
            raise AppError(404, f"行为树不存在 (name={name}){hint}")
        return tree

    # ------------------------------------------------------------- 变更

    def _resolver(self):
        return DbResolver(self.db)

    def _normalize(self, content: str) -> str:
        return normalize_tree_content(
            content, registry=self.registry, resolver=self._resolver()
        )

    def create(self, payload: TreeCreate) -> TreeOut:
        """API 直接创建（导入）：生成草稿，允许未通过校验。"""
        content = self._normalize(payload.content)
        tree = Tree(name=payload.name, content=content, status=STATUS_DRAFT)
        self.db.add(tree)
        self._commit_or_conflict()
        self.db.refresh(tree)
        return self._out(tree)

    def create_draft(self) -> TreeOut:
        """编辑器新建：临时名称 + 空树，状态 draft。"""
        name = self._temp_name()
        content = tree_doc.empty_document(name)
        tree = Tree(name=name, content=content, status=STATUS_DRAFT)
        self.db.add(tree)
        self._commit_or_conflict()
        self.db.refresh(tree)
        return self._out(tree)

    def update(self, tree_id: int, payload: TreeUpdate) -> TreeOut:
        """整文档更新（兼容旧 API）：改内容即转草稿，保存时再校验。"""
        tree = self.get(tree_id)
        new_name = payload.name if payload.name is not None else tree.name
        new_content = payload.content if payload.content is not None else tree.content
        new_content = self._normalize(new_content)
        if new_name != tree.name:
            new_content = self._rename_content(new_content, new_name)
        tree.name = new_name
        tree.content = new_content
        tree.status = STATUS_DRAFT
        self._commit_or_conflict()
        self.db.refresh(tree)
        return self._out(tree)

    def apply_commands(
        self, tree_id: int, commands: list[TreeCommand]
    ) -> tuple[TreeDetailOut, str | None]:
        """应用命令式编辑；返回最新完整文档与新节点 id。"""
        tree = self.get(tree_id)
        content, created_id, new_tree = tree_doc.apply_commands(
            tree.content,
            commands,
            registry=self.registry,
            resolver=self._resolver(),
        )
        if new_tree and new_tree != tree.name:
            content = self._rename_content(content, new_tree)
            tree.name = new_tree
        tree.content = content
        tree.status = STATUS_DRAFT
        self._commit_or_conflict()
        self.db.refresh(tree)
        return self.get_detail(tree_id), created_id

    def save(self, tree_id: int, name: str | None = None) -> TreeDetailOut:
        """保存：归一化 + 完整校验 + 改名 + 转正式。失败保持草稿。"""
        tree = self.get(tree_id)
        target_name = (name or tree.name).strip()
        content = self._normalize(tree.content)
        content = self._rename_content(content, target_name)
        # 校验使用即将发布的内容（由本服务注入 resolver；ref 目标需正式版）
        validate_document(content, target_name, registry=self.registry)
        tree.name = target_name
        tree.content = content
        tree.status = STATUS_PUBLISHED
        self._commit_or_conflict()
        self.db.refresh(tree)
        return self.get_detail(tree_id)

    def delete(self, tree_id: int) -> None:
        tree = self.get(tree_id)
        self.db.delete(tree)
        self.db.commit()

    # ------------------------------------------------------------- 内部

    def _temp_name(self) -> str:
        return f"未命名-{int(time.time() * 1000)}"

    @staticmethod
    def _rename_content(content: str, name: str) -> str:
        data = tree_doc.load(content)
        if data.get("tree") == name:
            return content
        data["tree"] = name
        return tree_doc.dump(data)

    def _commit_or_conflict(self) -> None:
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise AppError(409, "行为树名称已存在") from None


__all__ = ["TreeService"]
