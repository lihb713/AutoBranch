"""行为树文档 API schema（api-conventions.md §3.1）。

输入（Create/Update）显式声明 ``Field`` 约束让 FastAPI 自动返回 422；
输出（TreeOut/TreeDetailOut）只暴露客户端所需字段。
"""

from __future__ import annotations

from datetime import datetime

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
    #: 文档级入参声明（名 -> 类型），派生自 content（前端执行按钮约束/入参对话框用）。
    inputs: dict[str, str] = {}


class TreeDetailOut(TreeOut):
    content: str


__all__ = ["TreeCreate", "TreeUpdate", "TreeOut", "TreeDetailOut"]
