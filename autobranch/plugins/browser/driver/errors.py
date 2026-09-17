"""浏览器驱动可分类异常（契约 §9.4 按错误源分流）。

| 异常 | 错误源 | 语义 |
|---|---|---|
| ``BrowserError`` | 基类 | 浏览器驱动错误基类 |
| ``PageRefError`` | 无效页面引用 | 程序侧，调用方可捕获并转换 |
| ``FatalBrowserError`` | 浏览器崩溃/网络断开/context 关闭 | 致命，终止整个流程 |

按契约 §9.4 与 M1 spec §5.6：确定性程序侧失败（元素不存在、网络超时等）
返回 ``OpResult(ok=False)`` 携带分类错误码；致命错误（浏览器崩溃、网络断开、
context 关闭）抛出 ``FatalBrowserError`` 不吞没、不转换为失败结果。
"""

from __future__ import annotations


class BrowserError(Exception):
    """浏览器驱动错误基类。"""


class PageRefError(BrowserError):
    """无效/已释放的页面引用（程序侧错误，可捕获重试或终止）。"""


class FatalBrowserError(BrowserError):
    """致命错误：浏览器崩溃、网络断开、context 关闭。

    捕获后不得继续对死掉的浏览器操作，应终止整个执行流程。
    """
