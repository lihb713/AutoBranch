"""插件框架：加载器与源码校验（M3 spec 插件来源与组织）。

两条加载路径：

- **预置插件**：文件系统 ``plugins/`` 下的包，启动扫描 + ``import``（排除
  ``common`` 共享库）；包内以 ``plugin`` 变量暴露插件实例。
- **用户自定义插件**：源码存数据库，``compile + exec``（注入注册器）加载；
  仅标准库，不 import 其他插件 / ``common`` / 三方库。

``check_plugin_source`` 校验源码（语法 + 约束），返回可定位的错误明细
（行号 / 列号 / 类型 / 信息 / 约束）。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

from autobranch.plugin_system.defs import (
    FunctionResult,
    PluginBase,
    PluginError,
    engine_function,
)
from autobranch.plugin_system.registry import PluginRegistry

#: 共享库目录名（非插件，不注册、不对 LLM 暴露）。
COMMON_PACKAGE = "common"


def _iter_plugin_packages(plugins_dir: Path):
    """遍历预置插件子包（有 ``__init__.py`` 的目录，排除 common / 下划线）。"""
    if not plugins_dir.is_dir():
        return
    for entry in sorted(plugins_dir.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("_") or entry.name == COMMON_PACKAGE:
            continue
        if (entry / "__init__.py").is_file():
            yield entry


def load_builtin_plugins(
    registry: PluginRegistry,
    plugins_dir: str | Path,
    *,
    package_root: str = "autobranch.plugins",
) -> list[str]:
    """扫描 ``plugins/`` 子包并 import 注册；返回已注册插件名列表。

    单个插件加载失败不影响其他插件（记录并跳过）。
    """
    plugins_dir = Path(plugins_dir)
    loaded: list[str] = []
    for pkg_dir in _iter_plugin_packages(plugins_dir):
        module_name = f"{package_root}.{pkg_dir.name}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, pkg_dir / "__init__.py")
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            plugin = getattr(module, "plugin", None)
            if not isinstance(plugin, PluginBase):
                continue
            registry.register(plugin)
            loaded.append(plugin.name)
        except Exception as exc:  # noqa: BLE001 - 单插件失败不阻断其他
            sys.stderr.write(f"[plugin] 预置插件 {module_name} 加载失败: {exc}\n")
    return loaded


def load_plugin_from_source(
    registry: PluginRegistry,
    name: str,
    source: str,
    *,
    allow_override: bool = True,
) -> PluginBase:
    """从源码字符串加载自定义插件（``compile + exec``，注入注册器）。"""
    module = types.ModuleType(f"autobranch_custom_plugin_{name}")
    module.__dict__.update(
        {
            "__name__": f"autobranch_custom_plugin_{name}",
            "engine_function": engine_function,
            "PluginBase": PluginBase,
            "FunctionResult": FunctionResult,
        }
    )
    code = compile(source, f"<plugin:{name}>", "exec")
    exec(code, module.__dict__)  # noqa: S102 - 插件源码为受信开发者提供
    plugin = module.__dict__.get("plugin")
    if not isinstance(plugin, PluginBase):
        raise PluginError(f"插件 {name} 未定义 PluginBase 实例变量 'plugin'")
    if not plugin.name:
        plugin.name = name
    if plugin.name != name:
        raise PluginError(f"插件源码内 name={plugin.name!r} 与提交名 {name!r} 不一致")
    registry.register(plugin, allow_override=allow_override)
    return plugin


def _stdlib_names() -> set[str]:
    return set(getattr(sys, "stdlib_module_names", ()))


def _check_module(module: str, node: ast.AST, errors: list[dict[str, Any]]) -> None:
    """校验单个 import 模块：仅允许标准库。"""
    if not module:
        return
    top = module.split(".")[0]
    line = getattr(node, "lineno", None)
    col = getattr(node, "col_offset", None)
    if top == "plugins":
        errors.append(
            {
                "line": line,
                "column": col,
                "type": "constraint",
                "message": f"自定义插件不得引用其他插件 / common: {module}",
                "constraint": "仅标准库",
            }
        )
    elif top not in _stdlib_names():
        errors.append(
            {
                "line": line,
                "column": col,
                "type": "constraint",
                "message": f"自定义插件仅允许标准库，不允许 import {module}",
                "constraint": "仅标准库",
            }
        )


def check_plugin_source(source: str) -> tuple[bool, list[dict[str, Any]]]:
    """校验插件源码；返回 ``(ok, errors)``。

    错误项结构：``{line, column, type, message, constraint}``（供前端定位）。
    """
    errors: list[dict[str, Any]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        errors.append(
            {
                "line": exc.lineno,
                "column": exc.offset,
                "type": "syntax",
                "message": f"语法错误: {exc.msg}",
                "constraint": "Python 语法",
            }
        )
        return False, errors
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(alias.name, node, errors)
        elif isinstance(node, ast.ImportFrom):
            _check_module(node.module or "", node, errors)
    return not errors, errors


__all__ = [
    "COMMON_PACKAGE",
    "load_builtin_plugins",
    "load_plugin_from_source",
    "check_plugin_source",
]
