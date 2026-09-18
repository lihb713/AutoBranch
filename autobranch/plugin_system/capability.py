"""插件框架：两级能力选择（M3 spec 两级能力选择）。

- ``capability_overview``：能力概览文本（含各插件说明、函数清单、加载状态）。
- ``USE_CAPABILITY_TOOL``：框架工具（属插件框架，不属任何具体插件）。
- ``handle_use_capability``：处理能力加载，返回该能力函数清单（供工具集追加）。
"""

from __future__ import annotations

from typing import Any

from autobranch.llm import ToolSpec
from autobranch.plugin_system.defs import FunctionResult
from autobranch.plugin_system.registry import PluginRegistry

USE_CAPABILITY_TOOL = ToolSpec(
    name="use_capability",
    description=(
        "加载一个能力（插件）并返回其可用函数清单。能力加载后其函数即可调用。"
        "能力名必须逐字取自系统提示中的「可用能力」列表；臆造或改写名称将返回未知能力错误。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "capability": {
                "type": "string",
                "description": "要加载的能力名（逐字取自「可用能力」列表）",
            },
        },
        "required": ["capability"],
    },
)


def capability_overview(registry: PluginRegistry) -> str:
    """生成能力概览文本（供 LLM 一级选择）。"""
    plugins = registry.plugins()
    if not plugins:
        return "（无可用能力）"
    lines = ["可用能力: " + ", ".join(p.name for p in plugins)]
    for p in plugins:
        status = "已加载" if registry.is_loaded(p.name) else "未加载"
        funcs = ", ".join(s.full_name for s in registry.functions_of(p.name))
        desc = p.description or ""
        lines.append(f"- {p.name} [{status}]: {desc}" + (f" 函数: {funcs}" if funcs else ""))
    return "\n".join(lines)


def handle_use_capability(
    registry: PluginRegistry,
    args: dict[str, Any] | None,
    *,
    runtime: Any = None,
) -> FunctionResult:
    """处理 ``use_capability`` 调用：加载插件并返回其函数清单。

    返回值 ``detail["functions"]`` 为新增工具 schema 列表（供调用方追加进工具集）。
    """
    name = (args or {}).get("capability", "")
    if not name:
        return FunctionResult.failure("use_capability 需要 capability 参数")
    if name not in registry.known_plugins():
        return FunctionResult.failure(
            f"未知能力: {name}（可用: {', '.join(sorted(registry.known_plugins()))}）"
        )
    try:
        registry.ensure_loaded(name, runtime)
    except Exception as exc:  # noqa: BLE001 - 装配失败转失败结果
        return FunctionResult.failure(f"能力 {name} 加载失败: {exc}")
    funcs = registry.functions_of(name)
    return FunctionResult.success(
        report={
            "sections": [
                {
                    "title": f"能力 {name} 已加载",
                    "body": "、".join(s.full_name for s in funcs) if funcs else "（无函数）",
                }
            ]
        },
        capability=name,
        functions=[s.to_tool_spec() for s in funcs],
    )


__all__ = ["USE_CAPABILITY_TOOL", "capability_overview", "handle_use_capability"]
