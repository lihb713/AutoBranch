"""WebOps 报告机制（M8）。

记录行为树执行过程：所有节点退出前记录执行情况、Action/Condition 返回前截图，
流程结束生成两份报告（执行报告 + 回溯报告），并提供可查询的执行状态（§12.4）
与按 run_id 归组的持久化存储。依赖 M1（截图，经 ``screenshotter`` 注入）。
"""

from webops.reporting.models import (
    ActionCall,
    ExecReport,
    ExecState,
    LeafTrace,
    NodeInfo,
    NodeReport,
    ReportBundle,
    ToolCallRecord,
    TraceReport,
)
from webops.reporting.reporter import Reporter, sanitize_run_id, slugify

__all__ = [
    "Reporter",
    "sanitize_run_id",
    "slugify",
    "ActionCall",
    "ToolCallRecord",
    "LeafTrace",
    "NodeReport",
    "NodeInfo",
    "ExecState",
    "ExecReport",
    "TraceReport",
    "ReportBundle",
]
