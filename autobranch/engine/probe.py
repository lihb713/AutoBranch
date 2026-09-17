"""浏览器插件内部探针（兼容转发层）。

``EngineProbe`` 物理实现在 ``autobranch.plugins.browser.probe``（浏览器插件
自包含）；本模块仅为兼容而转发。
"""

from __future__ import annotations

import sys as _sys

import autobranch.plugins.browser.probe as _probe

_sys.modules[__name__] = _probe
