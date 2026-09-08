"""WebOps 浏览器驱动（M1）。

提供 WebOps 唯一接触真实浏览器的底层能力（模块地图阶段1、无依赖）：
- 会话生命周期：``BrowserDriver`` 每次 start 创建全新 context（冷启动、无
  持久化，契约 §5.9），stop 完整释放。
- 页面管理：``open`` 打开页面返回 ``PageRef`` 引用，``page`` 按引用取回
  ``PageHandle``，多页并存互不干扰（§5.10）。
- 页面操作：click/type/select/check/uncheck/scroll/wait，以及文件函数
  download/upload、截图 screenshot（§5.8.1/§5.8.3）。
- HTTP：形态A ``HttpRecorder`` 监听页面请求；形态B ``http_request`` 独立
  请求（§5.8.2）。
- DOM 爬取：``DomProbe.crawl`` 产出供 M4 使用的结构化快照（§8.3）。
- 数据契约与错误语义：``OpResult``/``ElementRef``/``PageRef``/``DomSnapshot``；
  程序侧失败返回可分类失败结果，致命错误抛出 ``FatalBrowserError``（§9.4）。
"""

from webops.browser.config import BrowserConfig
from webops.browser.dom import DomProbe
from webops.browser.driver import BrowserDriver
from webops.browser.errors import BrowserError, FatalBrowserError, PageRefError
from webops.browser.http import HttpRecorder, http_request
from webops.browser.models import (
    Bounds,
    DomSnapshot,
    ElementNode,
    ElementRef,
    ErrorCode,
    HttpResponse,
    LODSpec,
    OpResult,
    PageRef,
)

__all__ = [
    "BrowserConfig",
    "BrowserDriver",
    "DomProbe",
    "BrowserError",
    "FatalBrowserError",
    "PageRefError",
    "HttpRecorder",
    "http_request",
    "Bounds",
    "DomSnapshot",
    "ElementNode",
    "ElementRef",
    "ErrorCode",
    "HttpResponse",
    "LODSpec",
    "OpResult",
    "PageRef",
]
