"""浏览器插件内部 ref 映射（兼容转发层）。

``EngineRefMap`` 物理实现在 ``autobranch.plugins.browser.refmap``（浏览器插件
自包含）；本模块仅为兼容而转发。
"""

from __future__ import annotations

import sys as _sys

import autobranch.plugins.browser.refmap as _refmap

_sys.modules[__name__] = _refmap
