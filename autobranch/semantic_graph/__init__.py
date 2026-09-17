"""浏览器插件内部语义图（兼容转发层）。

语义图生成**物理实现在 ``autobranch.plugins.browser.semantic_graph``**（浏览器
插件自包含）；本模块仅为兼容而转发，供引擎核心 / 旧非插件路径引用。

顶层对象与全部子模块均指向插件内实现（避免同名子模块双加载）。
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

import autobranch.plugins.browser.semantic_graph as _sg

sys.modules[__name__] = _sg
for _mod in pkgutil.iter_modules(_sg.__path__):
    _full = f"autobranch.plugins.browser.semantic_graph.{_mod.name}"
    importlib.import_module(_full)
    sys.modules[f"{__name__}.{_mod.name}"] = sys.modules[_full]
