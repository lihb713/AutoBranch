"""行为树分组 API schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TreeGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="分组名称")


class TreeGroupUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="分组名称")


class TreeGroupOut(BaseModel):
    id: int
    name: str
    is_default: bool = False
    tree_count: int = 0


class TreeGroupMove(BaseModel):
    group_id: int


__all__ = ["TreeGroupCreate", "TreeGroupUpdate", "TreeGroupOut", "TreeGroupMove"]
