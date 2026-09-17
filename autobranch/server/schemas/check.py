"""清晰度校验报告 schema（契约 §4.4，错误清单可读）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CheckIssueOut(BaseModel):
    code: str
    message: str
    rule: str
    loc: str | None = None


class CheckReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool
    issues: list[CheckIssueOut] = []


__all__ = ["CheckIssueOut", "CheckReportOut"]
