"""行为树文档 API schema（api-conventions.md §3.1）。

输入（Create/Update）显式声明 ``Field`` 约束让 FastAPI 自动返回 422；
输出（TreeOut/TreeDetailOut）只暴露客户端所需字段。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TreeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="行为树名称（唯一）")
    content: str = Field(description="行为树文档 yaml 文本")


class TreeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = None

    @model_validator(mode="after")
    def _require_at_least_one(self) -> TreeUpdate:
        if self.name is None and self.content is None:
            raise ValueError("至少提供一个变更字段（name 或 content）")
        return self


class TreeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    #: 草稿/正式状态：``draft`` | ``published``。
    status: str = "published"
    #: 文档级入参声明（名 -> 类型），派生自 content（前端执行按钮约束/入参对话框用）。
    inputs: dict[str, str] = {}


class TreeDetailOut(TreeOut):
    content: str


class TreeCommand(BaseModel):
    """命令式编辑：后端应用命令并返回完整文档。"""

    op: Literal[
        "add_node",
        "delete_node",
        "update_node",
        "update_doc",
        "set_slot",
        "detach_slot",
    ]
    #: add_node 使用：节点类型（Action/Step/Sequence/...）。
    node_type: str | None = None
    #: delete_node/update_node 使用。
    node_id: str | None = None
    #: delete_node：是否连带删除后代。
    subtree: bool = False
    #: set_slot/detach_slot：槽位序号。
    slot_index: int | None = None
    #: set_slot：目标子节点 id（空字符串/None = 解引用）。
    child_id: str | None = None
    #: update_node/update_doc：字段更新。
    patch: dict[str, Any] | None = None


class TreeCommandsIn(BaseModel):
    commands: list[TreeCommand] = Field(min_length=1)


class TreeSaveIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class TreeCommandsOut(BaseModel):
    tree: TreeDetailOut
    created_node_id: str | None = None


__all__ = [
    "TreeCreate",
    "TreeUpdate",
    "TreeOut",
    "TreeDetailOut",
    "TreeCommand",
    "TreeCommandsIn",
    "TreeSaveIn",
    "TreeCommandsOut",
]
