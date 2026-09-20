"""经验回灌模型（Change C，experience-feedback）。

``experiences`` 表保存整树成功 run 的节点级成功经验（三钥匙身份 + 蒸馏内容），
供后续同条件（同执行结构 + 同入参 + 同节点）重跑时注入叶子 prompt。

- ``run_id`` 外键级联（删除执行实例时连带删除其经验）。
- 匹配组索引 ``(tree_content_hash, inputs_norm, node_desc)`` 支撑节点粒度惰性查询。
- ``tool_calls`` 存蒸馏后的成功调用序列（JSON），``decision`` 存最终决策文本。
"""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from autobranch.server.db import Base
from autobranch.server.models.mixins import TimestampMixin


class Experience(Base, TimestampMixin):
    """一条节点级成功经验（整树成功 run 中某叶子节点的蒸馏记录）。"""

    __tablename__ = "experiences"
    __table_args__ = (
        Index(
            "ix_experiences_match",
            "tree_content_hash",
            "inputs_norm",
            "node_desc",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tree_content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    inputs_norm: Mapped[str] = mapped_column(Text, nullable=False)
    node_desc: Mapped[str] = mapped_column(Text, nullable=False)
    node_type: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    tool_calls: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    decision: Mapped[str] = mapped_column(Text, nullable=False, default="")


__all__ = ["Experience"]
