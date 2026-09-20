"""执行相关 API schema（契约 §12.4 ExecState 数据契约 + Change A 实例化）。

``ExecStateOut`` 字段与 M8 ``ExecState`` 契约对齐：run_id / progress /
current_node / completed / finished，另附 failure_reason（执行失败时非空）。
``RunOut`` 为执行实例列表项（快照树名/入参/出参/指纹/耗时/进度）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RunStartIn(BaseModel):
    """执行触发请求体：可选根级入参值（名 -> JSON 值）。"""

    inputs: dict[str, Any] | None = None


class RunStartOut(BaseModel):
    run_id: int


class RunOut(BaseModel):
    """执行实例列表项。"""

    id: int
    tree_id: int | None = None
    tree_name: str = ""
    status: str
    inputs: dict[str, Any] = {}
    outputs: dict[str, Any] | None = None
    tree_content_hash: str = ""
    failure_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    duration: float | None = None
    progress: float | None = None


class RunDetailOut(RunOut):
    """执行实例详情（含快照内容，供"查看快照"）。"""

    content_snapshot: str = ""


class TypeInfoOut(BaseModel):
    """类型可构造性信息（GET /api/types）。"""

    token: str
    constructible: bool


class NodeInfoOut(BaseModel):
    node_type: str
    node_desc: str


class ActionCallOut(BaseModel):
    function: str
    success: bool
    arguments: dict | None = None
    error: str | None = None


class NodeReportOut(BaseModel):
    node_type: str
    node_desc: str
    result: str
    timestamp: str
    action_call: ActionCallOut | None = None
    condition_result: bool | None = None
    page_url: str | None = None
    screenshot_path: str | None = None


class ExecStateOut(BaseModel):
    run_id: str
    progress: float
    current_node: NodeInfoOut | None = None
    completed: list[NodeReportOut] = []
    finished: bool = False
    failure_reason: str | None = None
    variables: list[dict] = []


__all__ = [
    "RunStartIn",
    "RunStartOut",
    "RunOut",
    "RunDetailOut",
    "TypeInfoOut",
    "ExecStateOut",
    "NodeReportOut",
    "NodeInfoOut",
    "ActionCallOut",
]
