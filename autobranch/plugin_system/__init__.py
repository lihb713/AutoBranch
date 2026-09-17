"""插件框架（M3）：注册表 / 懒装配 / 两级能力选择 / 统一分发与报告接口。

引擎核心通过插件框架调用任意能力（浏览器 / 计算 / SSH / 文件…），
不感知具体插件实现。
"""

from autobranch.plugin_system.defs import (
    FunctionDef,
    FunctionResult,
    PluginBase,
    PluginError,
    engine_function,
)
from autobranch.plugin_system.loader import (
    COMMON_PACKAGE,
    check_plugin_source,
    load_builtin_plugins,
    load_plugin_from_source,
)
from autobranch.plugin_system.registry import PluginRegistry
from autobranch.plugin_system.reporting import collect_report_entries
from autobranch.plugin_system.runtime import PluginRuntime

__all__ = [
    "PluginError",
    "FunctionDef",
    "FunctionResult",
    "engine_function",
    "PluginBase",
    "PluginRegistry",
    "PluginRuntime",
    "COMMON_PACKAGE",
    "load_builtin_plugins",
    "load_plugin_from_source",
    "check_plugin_source",
    "collect_report_entries",
]
