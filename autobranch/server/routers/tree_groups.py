"""行为树分组路由。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from autobranch.server.schemas.tree_group import (
    TreeGroupCreate,
    TreeGroupOut,
    TreeGroupUpdate,
)
from autobranch.server.services.tree_groups import TreeGroupService

router = APIRouter(prefix="/api/tree-groups", tags=["tree-groups"])
TreeGroupServiceDep = Annotated[TreeGroupService, Depends()]


@router.get("", response_model=list[TreeGroupOut])
def list_groups(service: TreeGroupServiceDep):
    service.default_group()
    return service.list()


@router.post("", response_model=TreeGroupOut, status_code=status.HTTP_201_CREATED)
def create_group(payload: TreeGroupCreate, service: TreeGroupServiceDep):
    return service.create(payload.name)


@router.put("/{group_id}", response_model=TreeGroupOut)
def rename_group(group_id: int, payload: TreeGroupUpdate, service: TreeGroupServiceDep):
    return service.rename(group_id, payload.name)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: int, service: TreeGroupServiceDep):
    service.delete(group_id)


__all__ = ["router"]
