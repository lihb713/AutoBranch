"""执行相关 API schema（契约 §12.4 ExecState 数据契约）。

``ExecStateOut`` 字段与 M8 ``ExecState`` 契约对齐：run_id / progress /
current_node / completed / finished，另附 failure_reason（执行失败时非空）。
"""

from __future__ import annotations

from pydantic import BaseModel


class RunStartOut(BaseModel):
    run_id: int


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


__all__ = ["RunStartOut", "ExecStateOut", "NodeReportOut", "NodeInfoOut", "ActionCallOut"]
