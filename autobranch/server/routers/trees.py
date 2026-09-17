"""行为树文档路由（CRUD + 清晰度校验 + 执行触发）。

只做 HTTP 编排（状态码 / 参数 / service 调用），业务逻辑在 service 层。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from autobranch.server.db import get_db
from autobranch.server.deps import get_run_service
from autobranch.server.schemas.check import CheckReportOut
from autobranch.server.schemas.run import RunStartOut
from autobranch.server.schemas.tree import TreeCreate, TreeDetailOut, TreeOut, TreeUpdate
from autobranch.server.services.runs import RunService
from autobranch.server.services.trees import TreeService
from autobranch.server.services.validation import CheckReportBuilder, validate_document

router = APIRouter(prefix="/api/trees", tags=["trees"])

TreeServiceDep = Annotated[TreeService, Depends()]
RunServiceDep = Annotated[RunService, Depends(get_run_service)]
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[TreeOut])
def list_trees(service: TreeServiceDep):
    return service.list_all()


@router.post("", response_model=TreeOut, status_code=status.HTTP_201_CREATED)
def create_tree(payload: TreeCreate, service: TreeServiceDep):
    return service.create(payload)


@router.get("/by-name/{name}", response_model=TreeDetailOut)
def get_tree_by_name(name: str, service: TreeServiceDep):
    """按文档名查（文档名唯一）：供跨文档引用加载 / ref 展开。"""
    return TreeDetailOut.model_validate(service.get_by_name(name))


@router.get("/{tree_id}", response_model=TreeDetailOut)
def get_tree(tree_id: int, service: TreeServiceDep):
    return service.get_detail(tree_id)


@router.put("/{tree_id}", response_model=TreeOut)
def update_tree(tree_id: int, payload: TreeUpdate, service: TreeServiceDep):
    return service.update(tree_id, payload)


@router.delete("/{tree_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tree(tree_id: int, service: TreeServiceDep):
    service.delete(tree_id)


@router.post("/{tree_id}/check", response_model=CheckReportOut)
def check_tree(tree_id: int, service: TreeServiceDep):
    """清晰度校验（复用 M2）：返回校验报告，不落库。"""
    tree = service.get(tree_id)
    return CheckReportBuilder.build(tree.content, tree.name, registry=service.registry)


@router.post("/{tree_id}/run", response_model=RunStartOut, status_code=status.HTTP_202_ACCEPTED)
def run_tree(
    tree_id: int,
    background_tasks: BackgroundTasks,
    service: TreeServiceDep,
    run_service: RunServiceDep,
    db: DbSession,
):
    """异步触发执行：执行前校验（422 拒绝）→ 建 Run → 后台任务内嵌引擎。"""
    tree = service.get(tree_id)
    validate_document(tree.content, tree.name, registry=service.registry)
    run = run_service.start(db, tree_id)
    background_tasks.add_task(run_service.execute_async, run.id, tree_id)
    return {"run_id": run.id}


__all__ = ["router"]
