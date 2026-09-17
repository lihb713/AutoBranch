"""插件管理 API schema（plugin-management spec）。

输入（Create/Update/CheckIn）显式声明约束让 FastAPI 自动 422；输出暴露
插件元数据与（自定义）源码。
"""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_NAME_PATTERN = r"^[a-z][a-z0-9_-]*$"


class PluginCreate(BaseModel):
    name: str = Field(
        min_length=1, max_length=128, pattern=_NAME_PATTERN, description="插件名（kebab-case）"
    )
    source: str = Field(description="插件源码（仅标准库）")


class PluginUpdate(BaseModel):
    source: str = Field(description="插件源码（仅标准库）")


class PluginCheckIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    source: str = Field(description="待校验的插件源码")


class PluginOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    description: str
    functions: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("functions", mode="before")
    @classmethod
    def _parse_functions(cls, value):
        if isinstance(value, str):
            try:
                data = json.loads(value) if value else []
            except (ValueError, TypeError):
                return []
            return data if isinstance(data, list) else []
        return value


class PluginDetailOut(PluginOut):
    source: str | None = None


class FunctionInfo(BaseModel):
    """函数清单条目（``GET /api/functions``）：全名 + 所属插件 + 结构化定义。"""

    full_name: str
    plugin: str
    name: str
    description: str = ""
    returns: list[str] = Field(default_factory=list)
    parameters: dict = Field(default_factory=dict)


class PluginCheckError(BaseModel):
    line: int | None = None
    column: int | None = None
    type: str
    message: str
    constraint: str = ""


class PluginCheckOut(BaseModel):
    ok: bool
    errors: list[PluginCheckError] = Field(default_factory=list)


class PluginDeleteOut(BaseModel):
    """删除结果：受影响（引用被置空）的行为树名列表。"""

    affected_trees: list[str] = Field(default_factory=list)


__all__ = [
    "PluginCreate",
    "PluginUpdate",
    "PluginCheckIn",
    "PluginOut",
    "PluginDetailOut",
    "FunctionInfo",
    "PluginCheckError",
    "PluginCheckOut",
    "PluginDeleteOut",
]
