"""浏览器插件内部驱动（兼容转发层）。

浏览器驱动**物理实现在 ``autobranch.plugins.browser.driver``**（浏览器插件自包含）；
本模块仅为兼容而转发，供引擎核心 / 旧非插件路径引用（后续可渐进移除）。

顶层对象与全部子模块均指向插件内实现（避免同名子模块双加载）。
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

import autobranch.plugins.browser.driver as _driver

sys.modules[__name__] = _driver
for _mod in pkgutil.iter_modules(_driver.__path__):
    _full = f"autobranch.plugins.browser.driver.{_mod.name}"
    importlib.import_module(_full)
    sys.modules[f"{__name__}.{_mod.name}"] = sys.modules[_full]
