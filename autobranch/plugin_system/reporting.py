"""插件框架：统一 reporting 接口（M3 spec 统一 reporting 接口）。

插件函数通过**返回值**携带报告附加信息（``FunctionResult.report``），引擎
落笔写入报告（按来源分组）；插件不直接调用报告器。本模块提供从
``FunctionResult`` 提取报告条目的辅助。
"""

from __future__ import annotations

from typing import Any

from autobranch.plugin_system.defs import FunctionResult


def collect_report_entries(result: FunctionResult, plugin_name: str) -> list[dict[str, Any]]:
    """把函数结果的报告附加信息转为按来源分组的条目。

    返回 ``[{"source": plugin_name, "sections": [...]}]``；无报告信息返回空列表。
    """
    if not result.report or not result.report.get("sections"):
        return []
    return [{"source": plugin_name, "sections": list(result.report["sections"])}]


__all__ = ["collect_report_entries"]
