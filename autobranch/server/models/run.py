"""执行实例模型（database-rules.md §2.3/§3.1，Change A 快照化）。

``status`` 以 CheckConstraint 约束枚举（pending/running/success/failure），
``tree_id`` 外键 SET NULL（删除行为树时**保留**执行历史，历史自包含），
``content_snapshot``/``tree_name_snapshot``/``tree_content_hash`` 为触发时刻
冻结的行为树快照（执行/重试/经验匹配依据），``inputs``/``outputs`` 存 JSON
安全入参/出参，``report_path`` 存报告相对路径（大字段落盘不入库，database-rules §6）。
"""

from __future__ import annotations

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from autobranch.server.db import Base
from autobranch.server.models.mixins import TimestampMixin

#: 执行状态枚举（与数据库 CheckConstraint 一致）。
RUN_STATUSES = ("pending", "running", "success", "failure")


class Run(Base, TimestampMixin):
    """一次执行实例（含触发时刻冻结的行为树快照与入参）。"""

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','success','failure')", name="ck_runs_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tree_id: Mapped[int | None] = mapped_column(
        ForeignKey("trees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tree_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    tree_content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", index=True
    )
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    outputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)


__all__ = ["Run", "RUN_STATUSES"]
