"""执行记录模型（database-rules.md §2.3/§3.1）。

``status`` 以 CheckConstraint 约束枚举（pending/running/success/failure），
``tree_id`` 外键级联（删除行为树时连带删除其执行记录），``report_path``
存报告相对路径（大字段落盘不入库，database-rules §6）。
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from autobranch.server.db import Base
from autobranch.server.models.mixins import TimestampMixin

#: 执行状态枚举（与数据库 CheckConstraint 一致）。
RUN_STATUSES = ("pending", "running", "success", "failure")


class Run(Base, TimestampMixin):
    """一次执行记录。"""

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','success','failure')", name="ck_runs_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tree_id: Mapped[int] = mapped_column(
        ForeignKey("trees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)


__all__ = ["Run", "RUN_STATUSES"]
