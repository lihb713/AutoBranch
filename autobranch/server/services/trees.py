"""行为树文档 CRUD 服务（设计 D1：业务逻辑下沉 service 层）。

业务规则：重名 409、不存在 404（抛 ``AppError``）；保存前经 M2 清晰度校验
（``validate_document``，失败 422 不落库，契约 §12.5）；删除行为树时**保留**
其历史执行实例（``Run.tree_id`` 经 FK ``SET NULL`` 置空，执行历史自包含）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from autobranch.plugin_system import PluginRegistry
from autobranch.server.db import get_db
from autobranch.server.deps import get_plugin_registry
from autobranch.server.errors import AppError
from autobranch.server.models import Tree
from autobranch.server.schemas.tree import TreeCreate, TreeDetailOut, TreeOut, TreeUpdate
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
        """派生文档级入参声明（名 -> 类型），供前端执行约束/入参对话框。"""
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
            inputs=self._declared_inputs(tree.content),
        )

    def list_all(self) -> list[TreeOut]:
        trees = self.db.scalars(select(Tree).order_by(Tree.id)).all()
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
            inputs=out.inputs,
            content=tree.content,
        )

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
        validate_document(payload.content, payload.name, registry=self.registry)
        tree = Tree(name=payload.name, content=payload.content)
        self.db.add(tree)
        self._commit_or_conflict()
        self.db.refresh(tree)
        return self._out(tree)

    def update(self, tree_id: int, payload: TreeUpdate) -> TreeOut:
        tree = self.get(tree_id)
        new_name = payload.name if payload.name is not None else tree.name
        new_content = payload.content if payload.content is not None else tree.content
        validate_document(new_content, new_name, registry=self.registry)
        tree.name = new_name
        tree.content = new_content
        self._commit_or_conflict()
        self.db.refresh(tree)
        return self._out(tree)

    def delete(self, tree_id: int) -> None:
        tree = self.get(tree_id)
        self.db.delete(tree)
        self.db.commit()

    # ------------------------------------------------------------- 内部

    def _commit_or_conflict(self) -> None:
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise AppError(409, "行为树名称已存在") from None


__all__ = ["TreeService"]
