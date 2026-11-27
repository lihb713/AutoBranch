"""行为树分组服务。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from autobranch.server.db import get_db
from autobranch.server.errors import AppError
from autobranch.server.models import Tree, TreeGroup
from autobranch.server.schemas.tree_group import TreeGroupOut

DbSession = Annotated[Session, Depends(get_db)]

DEFAULT_GROUP_NAME = "默认分组"


class TreeGroupService:
    """分组 CRUD 与默认分组保证。"""

    def __init__(self, db: DbSession) -> None:
        self.db = db

    def default_group(self) -> TreeGroup:
        group = self.db.scalars(
            select(TreeGroup).where(TreeGroup.is_default.is_(True)).order_by(TreeGroup.id)
        ).first()
        if group is not None:
            return group
        group = TreeGroup(name=DEFAULT_GROUP_NAME, is_default=True)
        self.db.add(group)
        self._commit_or_conflict()
        self.db.refresh(group)
        return group

    def resolve(self, group_id: int | None) -> TreeGroup:
        if group_id is None:
            return self.default_group()
        group = self.db.get(TreeGroup, group_id)
        if group is None:
            raise AppError(404, f"分组不存在 (id={group_id})")
        return group

    def list(self) -> list[TreeGroupOut]:
        rows = self.db.execute(
            select(TreeGroup, func.count(Tree.id))
            .outerjoin(Tree, Tree.group_id == TreeGroup.id)
            .group_by(TreeGroup.id)
            .order_by(TreeGroup.is_default.desc(), TreeGroup.id)
        ).all()
        return [
            TreeGroupOut(
                id=group.id,
                name=group.name,
                is_default=group.is_default,
                tree_count=count,
            )
            for group, count in rows
        ]

    def create(self, name: str) -> TreeGroupOut:
        cleaned = self._clean_name(name)
        group = TreeGroup(name=cleaned, is_default=False)
        self.db.add(group)
        self._commit_or_conflict()
        self.db.refresh(group)
        return TreeGroupOut(id=group.id, name=group.name, is_default=False, tree_count=0)

    def rename(self, group_id: int, name: str) -> TreeGroupOut:
        group = self.resolve(group_id)
        group.name = self._clean_name(name)
        self._commit_or_conflict()
        self.db.refresh(group)
        return TreeGroupOut(
            id=group.id,
            name=group.name,
            is_default=group.is_default,
            tree_count=self._count(group.id),
        )

    def delete(self, group_id: int) -> None:
        """删除分组；组内行为树移动到默认分组。"""
        group = self.resolve(group_id)
        if group.is_default:
            raise AppError(403, "默认分组不可删除")
        default = self.default_group()
        self.db.execute(
            update(Tree).where(Tree.group_id == group.id).values(group_id=default.id)
        )
        self.db.delete(group)
        self.db.commit()

    @staticmethod
    def _clean_name(name: str) -> str:
        cleaned = str(name or "").strip()
        if not cleaned:
            raise AppError(422, "分组名称不能为空")
        return cleaned

    def _count(self, group_id: int) -> int:
        return int(
            self.db.scalar(select(func.count(Tree.id)).where(Tree.group_id == group_id)) or 0
        )

    def _commit_or_conflict(self) -> None:
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise AppError(409, "分组名称已存在") from None


__all__ = ["TreeGroupService", "DEFAULT_GROUP_NAME"]
