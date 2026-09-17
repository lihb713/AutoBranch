"""插件框架：注册表与统一分发（M3 spec 统一分发与产出型工具 / 懒装配）。

``PluginRegistry`` 维护三张表：

- ``_plugins``：插件名 → 插件实例（known）。
- ``_functions`` / ``_owner``：**函数全名**（``插件名.函数名``）→ 函数定义 /
  所属插件（同一插件内函数名唯一，跨插件允许同名）。
- ``_loaded``：已 ``init`` 的插件名。

分发（``call``）按函数全名定位插件 → 懒装配 → 调用。同插件内函数重名在注册时拒绝。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from autobranch.plugin_system.defs import (
    FunctionDef,
    FunctionResult,
    PluginBase,
    PluginError,
)


class PluginRegistry:
    """插件注册表：注册 / 懒装配 / 分发 / 函数查询。"""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginBase] = {}
        self._functions: dict[str, FunctionDef] = {}
        self._owner: dict[str, str] = {}
        self._loaded: set[str] = set()

    # ------------------------------------------------------------ 注册

    def register(self, plugin: PluginBase, *, allow_override: bool = False) -> PluginBase:
        """注册插件及其函数；同一插件内函数名唯一，重名默认拒绝。

        跨插件允许同名函数（全名 ``插件名.函数名`` 不同，不视为冲突）；
        同一插件重复注册视为重载（幂等覆盖，供引擎每次 run 重载预置插件）。
        """
        if not getattr(plugin, "name", ""):
            raise PluginError("插件缺少 name")
        for spec in plugin.function_defs():
            full = f"{plugin.name}.{spec.name}"
            existing = self._owner.get(full)
            if existing is not None and existing != plugin.name and not allow_override:
                raise PluginError(f"函数重名: {full} 已属插件 {existing}")
            self._functions[full] = replace(spec, plugin=plugin.name)
            self._owner[full] = plugin.name
        self._plugins[plugin.name] = plugin
        return plugin

    def unregister(self, name: str) -> None:
        """注销插件及其函数（供插件管理重载 / 删除）。"""
        plugin = self._plugins.pop(name, None)
        if plugin is None:
            return
        for spec in plugin.function_defs():
            full = f"{name}.{spec.name}"
            if self._owner.get(full) == name:
                self._owner.pop(full, None)
                self._functions.pop(full, None)
        self._loaded.discard(name)

    # ------------------------------------------------------------ 查询

    def known_plugins(self) -> set[str]:
        return set(self._plugins)

    def loaded_plugins(self) -> set[str]:
        return set(self._loaded)

    def plugins(self) -> list[PluginBase]:
        return list(self._plugins.values())

    def plugin(self, name: str) -> PluginBase | None:
        return self._plugins.get(name)

    def is_loaded(self, name: str) -> bool:
        return name in self._loaded

    def function(self, full_name: str) -> FunctionDef | None:
        return self._functions.get(full_name)

    def owner(self, full_name: str) -> str | None:
        return self._owner.get(full_name)

    def functions(self) -> dict[str, FunctionDef]:
        return dict(self._functions)

    def functions_of(self, plugin_name: str) -> list[FunctionDef]:
        return [s for s in self._functions.values() if self._owner[s.full_name] == plugin_name]

    def loaded_functions(self) -> list[FunctionDef]:
        """已加载插件的函数（供 LLM 工具集）。"""
        return [s for s in self._functions.values() if self._owner[s.full_name] in self._loaded]

    # ------------------------------------------------------------ 懒装配 / 分发

    def ensure_loaded(self, plugin_name: str, runtime: Any = None) -> PluginBase:
        """懒装配：插件未 ``init`` 则初始化（重资源在此启动）。"""
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            raise PluginError(f"未注册插件: {plugin_name}")
        if plugin_name not in self._loaded:
            plugin.init(runtime)
            self._loaded.add(plugin_name)
        return plugin

    def release(self) -> None:
        """释放全部已装配插件（运行结束统一释放，含提前终止）。"""
        for name in list(self._loaded):
            plugin = self._plugins.get(name)
            if plugin is None:
                continue
            closer = getattr(plugin, "release", None)
            if callable(closer):
                try:
                    closer()
                except Exception:  # noqa: BLE001 - 释放不应阻断其他插件
                    pass
        self._loaded.clear()

    def call(
        self,
        full_name: str,
        args: dict[str, Any] | None = None,
        *,
        runtime: Any = None,
    ) -> FunctionResult:
        """统一分发：按函数全名定位插件 → 懒装配 → 以裸函数名调用。"""
        spec = self._functions.get(full_name)
        if spec is None:
            return FunctionResult.failure(f"未知函数: {full_name}")
        owner = self._owner[full_name]
        try:
            plugin = self.ensure_loaded(owner, runtime)
        except Exception as exc:  # noqa: BLE001 - 装配失败转失败结果
            return FunctionResult.failure(f"插件 {owner} 加载失败: {exc}")
        return plugin.call(spec.name, args)


__all__ = ["PluginRegistry"]
