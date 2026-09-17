"""浏览器驱动（M1）：会话生命周期、页面引用与页面操作（M1 spec §5.1/§5.2）。

设计要点（见 design.md）：
- ``BrowserDriver.start`` 每次创建全新 context（冷启动、无持久化，契约 §5.9），
  ``stop`` 完整释放 context 与全部页面。
- ``open`` / ``page`` 返回 ``OpResult``，成功时 ``detail`` 携带产物（PageRef /
  PageHandle）——失败时才能返回携带分类错误码的失败结果（契约 §9.4）。
- 所有页面操作显式绑定页面引用（§5.10），无效/已释放引用返回失败而非作用其他页。
- 程序侧失败（元素不存在/超时等）返回 ``ok=False`` + 分类错误码；致命错误
  （浏览器崩溃/网络断开/context 关闭）抛出 ``FatalBrowserError``（§9.4 设计 D8）。
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from autobranch.plugins.browser.driver.config import BrowserConfig
from autobranch.plugins.browser.driver.errors import BrowserError, FatalBrowserError, PageRefError
from autobranch.plugins.browser.driver.http import HttpRecorder
from autobranch.plugins.browser.driver.models import ElementRef, ErrorCode, OpResult, PageRef

_FATAL_KEYWORDS = (
    "target closed",
    "target page, context or browser has been closed",
    "browser has been closed",
    "browser process has been closed",
    "context destroyed",
    "connection closed",
    "connection is closed",
    "execution context was destroyed",
    "event loop is closed",
    "already stopped",
)


def _classify_playwright_error(exc: Exception) -> tuple[str | None, str]:
    """把 Playwright 异常映射为（错误码 或 "FATAL"，错误信息）。

    致命关键词命中 → "FATAL"（设计 D8）；否则按 timeout 日志细分程序侧错误码。
    """
    message = str(exc)
    lowered = message.lower()
    if any(k in lowered for k in _FATAL_KEYWORDS):
        return "FATAL", message
    if isinstance(exc, PlaywrightTimeoutError):
        if "locator resolved to" in message:
            if "disabled" in lowered:
                return ErrorCode.NOT_ENABLED, message
            if "hidden" in lowered:
                return ErrorCode.NOT_VISIBLE, message
            if "pointer events" in lowered or "not stable" in lowered:
                return ErrorCode.NOT_INTERACTABLE, message
            if "not attached" in lowered:
                return ErrorCode.NOT_FOUND, message
            if "editable" in lowered:
                return ErrorCode.NOT_EDITABLE, message
            return ErrorCode.TIMEOUT, message
        return ErrorCode.NOT_FOUND, message
    if "strict mode violation" in lowered:
        return ErrorCode.AMBIGUOUS, message
    if "not attached" in lowered:
        return ErrorCode.NOT_FOUND, message
    if "not an <input>" in lowered or "contenteditable" in lowered:
        return ErrorCode.NOT_EDITABLE, message
    if "is not a <select>" in lowered:
        return ErrorCode.NOT_INTERACTABLE, message
    return ErrorCode.UNKNOWN, message


# 在页面内解析 select 的选项匹配方式（label 或 value），返回 {"match": ...} 或 None
_RESOLVE_OPTION_JS = """(args) => {
  const el = document.querySelector(args.sel);
  if (!el) return null;
  if (el.tagName.toLowerCase() !== 'select') return { match: null };
  for (const o of el.options) {
    if ((o.textContent || '').trim() === args.opt) return { match: 'label' };
    if (o.value === args.opt) return { match: 'value' };
  }
  return { match: null };
}
"""

_SCROLL_DELTA = 500
_PUMP_MS = 50


class BrowserDriver:
    """浏览器会话管理器（M1 spec §5.1）。

    每次 ``start`` 创建全新 context；``open`` 打开页面返回引用；``page`` 按引用
    取回 ``PageHandle``；``stop`` 完整释放。
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._config: BrowserConfig | None = None
        self._pages: dict[str, Page] = {}
        self._next_page_id = 1
        self._http_recorder = HttpRecorder()
        self._active_id: str | None = None

    # ------------------------------------------------------------------ 会话

    def start(self, config: BrowserConfig | None = None) -> None:
        """创建全新浏览器 context（冷启动，契约 §5.9）。

        若已有会话则先完整释放（可重复调用），保证第二次 start 无上一次的
        cookie/localStorage/登录态。
        """
        self.stop()
        cfg = config or BrowserConfig()
        playwright = sync_playwright().start()
        browser_type = getattr(playwright, cfg.browser_type)
        browser = browser_type.launch(headless=cfg.headless)
        context = browser.new_context()
        context.on("response", self._http_recorder.record_response)
        self._playwright = playwright
        self._browser = browser
        self._context = context
        self._config = cfg
        self._pages = {}
        # 页面 id 驱动级单调递增（跨会话不重置），避免重启后旧引用误绑定新页
        self._http_recorder.clear()
        self._http_recorder.pump = self._pump_events

    def stop(self) -> None:
        """释放 context 与全部页面（契约 §5.9：会话结束释放全部资源）。

        页面引用随之全部失效；幂等，重复调用安全。
        """
        for page in list(self._pages.values()):
            try:
                page.close()
            except Exception:
                pass
        self._pages = {}
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._http_recorder.clear()
        self._http_recorder.pump = None

    @property
    def running(self) -> bool:
        return self._context is not None

    @property
    def http_recorder(self) -> HttpRecorder:
        """形态A 页面请求监听器（契约 §5.8.2）。"""
        return self._http_recorder

    def _timeout(self) -> int:
        return self._config.timeout_ms if self._config else 30000

    def _pump_events(self) -> None:
        """短暂阻塞运行 sync 事件循环，派发 pending 的 response 事件。

        Playwright sync API 的 asyncio 循环只在主线程的 API 调用期间运行；
        用任意存活页面的 ``wait_for_timeout`` 撑开一个时间窗让事件到达。
        """
        for page in list(self._pages.values()):
            try:
                page.wait_for_timeout(_PUMP_MS)
            except Exception:
                continue
            return

    # ------------------------------------------------------------------ 页面

    def open(self, url: str, timeout_ms: int | None = None) -> OpResult:
        """打开页面并返回页面引用（成功时 ``detail["page_ref"]``）。

        加载超时/地址不可达返回 ``ok=False`` + 分类错误码，不产出可用引用；
        浏览器致命错误抛出 ``FatalBrowserError``。
        """
        if self._context is None:
            return OpResult(False, "浏览器会话未启动", {"code": ErrorCode.SESSION_NOT_RUNNING})
        timeout = timeout_ms or self._timeout()
        page = self._context.new_page()
        try:
            # wait_until="domcontentloaded"：重型/流式页面（如 opencode.ai）的 "load"
            # 事件可能永不触发，导致 goto 一直挂到超时；domcontentloaded 在 HTML
            # 解析完成即返回，动态内容由后续 semantic_graph 读取。
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        except PlaywrightTimeoutError as exc:
            self._safe_close_page(page)
            code = ErrorCode.NETWORK if "err_" in str(exc).lower() else ErrorCode.LOAD_TIMEOUT
            return OpResult(False, f"打开页面失败: {exc}", {"code": code, "url": url})
        except PlaywrightError as exc:
            self._safe_close_page(page)
            code, message = _classify_playwright_error(exc)
            if code == "FATAL":
                raise FatalBrowserError(f"浏览器致命错误: {message}") from exc
            if "err_" in message.lower():
                code = ErrorCode.NETWORK
            return OpResult(
                False,
                f"打开页面失败: {message}",
                {"code": code or ErrorCode.NETWORK, "url": url},
            )
        ref_id = str(self._next_page_id)
        self._next_page_id += 1
        self._pages[ref_id] = page
        self._active_id = ref_id
        return OpResult(True, detail={"page_ref": PageRef(ref_id), "url": url})

    def page(self, page_ref: PageRef) -> OpResult:
        """按页面引用取回页面句柄（成功时 ``detail["page"]`` 为 PageHandle）。

        引用无效/已释放返回 ``ok=False`` + INVALID_REF，不作用于任何页面。
        """
        if self._context is None:
            return OpResult(False, "浏览器会话未启动", {"code": ErrorCode.SESSION_NOT_RUNNING})
        page = self._pages.get(page_ref.id)
        if page is None:
            return OpResult(False, f"无效页面引用: {page_ref.id}", {"code": ErrorCode.INVALID_REF})
        try:
            _ = page.url
        except PlaywrightError as exc:
            code, message = _classify_playwright_error(exc)
            self._pages.pop(page_ref.id, None)
            if code == "FATAL":
                raise FatalBrowserError(f"浏览器致命错误: {message}") from exc
            return OpResult(False, f"页面已释放: {page_ref.id}", {"code": ErrorCode.INVALID_REF})
        return OpResult(True, detail={"page": PageHandle(self, page, page_ref)})

    def current_page(self) -> PageRef | None:
        """返回当前活动页引用（最近 open/activate 的页；无则 None）。"""
        if self._context is None or self._active_id is None:
            return None
        if self._active_id not in self._pages:
            return None
        return PageRef(self._active_id)

    def activate_page(self, page_ref: PageRef) -> OpResult:
        """把已打开的页设为当前活动页（bring_to_front），后续操作作用于该页。"""
        if self._context is None:
            return OpResult(False, "浏览器会话未启动", {"code": ErrorCode.SESSION_NOT_RUNNING})
        page = self._pages.get(page_ref.id)
        if page is None:
            return OpResult(False, f"无效页面引用: {page_ref.id}", {"code": ErrorCode.INVALID_REF})
        try:
            page.bring_to_front()
        except PlaywrightError as exc:
            code, message = _classify_playwright_error(exc)
            self._pages.pop(page_ref.id, None)
            if code == "FATAL":
                raise FatalBrowserError(f"浏览器致命错误: {message}") from exc
            return OpResult(False, f"页面已释放: {page_ref.id}", {"code": ErrorCode.INVALID_REF})
        self._active_id = page_ref.id
        return OpResult(True, detail={"page_ref": page_ref})

    def _safe_close_page(self, page: Page) -> None:
        try:
            page.close()
        except Exception:
            pass

    def _resolve_page(self, page_ref: PageRef) -> Page:
        """供 DomProbe 等内部使用：解析页面引用，失败抛可分类异常。"""
        if self._context is None:
            raise BrowserError("浏览器会话未启动")
        page = self._pages.get(page_ref.id)
        if page is None:
            raise PageRefError(f"无效页面引用: {page_ref.id}")
        try:
            _ = page.url
        except PlaywrightError as exc:
            code, message = _classify_playwright_error(exc)
            self._pages.pop(page_ref.id, None)
            if code == "FATAL":
                raise FatalBrowserError(f"浏览器致命错误: {message}") from exc
            raise PageRefError(f"页面已释放: {page_ref.id}") from exc
        return page


class PageHandle:
    """绑定到指定页面的操作句柄（M1 spec §5.2，设计 D4：操作显式绑定页面引用）。"""

    def __init__(self, driver: BrowserDriver, page: Page, page_ref: PageRef) -> None:
        self._driver = driver
        self._page = page
        self._page_ref = page_ref
        self._timeout_ms = driver._timeout()

    @property
    def page_ref(self) -> PageRef:
        return self._page_ref

    @property
    def url(self) -> str:
        return self._page.url

    @property
    def title(self) -> str:
        return self._page.title()

    # ------------------------------------------------------------------ 辅助

    def _guard(self, fn: Callable[[], Any]) -> OpResult:
        """执行操作并把程序侧异常分类为失败结果；致命错误上抛。"""
        try:
            fn()
        except PlaywrightTimeoutError as exc:
            return self._fail(exc)
        except PlaywrightError as exc:
            return self._fail(exc)
        return OpResult(True, detail={"page_ref": self._page_ref})

    def _fail(self, exc: Exception) -> OpResult:
        code, message = _classify_playwright_error(exc)
        if code == "FATAL":
            raise FatalBrowserError(f"浏览器致命错误: {message}") from exc
        return OpResult(False, message, {"code": code, "page_ref": self._page_ref})

    def _locator(self, ref: ElementRef):
        return self._page.locator(ref.id)

    # ------------------------------------------------------------------ 操作

    def click(self, ref: ElementRef) -> OpResult:
        """点击元素（触发其点击行为，任务 4.1）。"""
        return self._guard(lambda: self._locator(ref).click(timeout=self._timeout_ms))

    def type(self, ref: ElementRef, text: str) -> OpResult:
        """向文本输入类元素输入文本（替换现有值，任务 4.1）。"""
        return self._guard(lambda: self._locator(ref).fill(text, timeout=self._timeout_ms))

    def select(self, ref: ElementRef, option: str) -> OpResult:
        """下拉选择：优先按选项文本（label）匹配，其次按 value 匹配（任务 4.2）。"""
        if not isinstance(option, str) or not option:
            return OpResult(
                False,
                "选项不能为空",
                {"code": ErrorCode.INVALID_ARGUMENT, "page_ref": self._page_ref},
            )
        try:
            choice = self._page.evaluate(_RESOLVE_OPTION_JS, {"sel": ref.id, "opt": option})
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            return self._fail(exc)
        if choice is None:
            return OpResult(
                False,
                f"元素不存在: {ref.id}",
                {"code": ErrorCode.NOT_FOUND, "page_ref": self._page_ref},
            )
        if choice.get("match") is None:
            return OpResult(
                False,
                f"选项中不存在: {option}",
                {"code": ErrorCode.NOT_FOUND, "page_ref": self._page_ref},
            )
        try:
            if choice["match"] == "label":
                self._locator(ref).select_option(label=option, timeout=self._timeout_ms)
            else:
                self._locator(ref).select_option(value=option, timeout=self._timeout_ms)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            return self._fail(exc)
        return OpResult(True, detail={"page_ref": self._page_ref})

    def check(self, ref: ElementRef) -> OpResult:
        """勾选勾选类控件（任务 4.2）。"""
        return self._guard(lambda: self._locator(ref).check(timeout=self._timeout_ms))

    def uncheck(self, ref: ElementRef) -> OpResult:
        """取消勾选勾选类控件（任务 4.2）。"""
        return self._guard(lambda: self._locator(ref).uncheck(timeout=self._timeout_ms))

    _SCROLLS = ("up", "down", "left", "right", "top", "bottom")

    def scroll(self, direction: str) -> OpResult:
        """滚动页面（up/down/left/right/top/bottom，任务 4.3）。"""
        if direction not in self._SCROLLS:
            return OpResult(
                False,
                f"非法滚动方向: {direction}（应为 {'/'.join(self._SCROLLS)}）",
                {"code": ErrorCode.INVALID_ARGUMENT, "page_ref": self._page_ref},
            )
        try:
            if direction == "top":
                self._page.evaluate("window.scrollTo(0, 0)")
            elif direction == "bottom":
                self._page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
            elif direction in ("left", "right"):
                delta = _SCROLL_DELTA if direction == "right" else -_SCROLL_DELTA
                self._page.evaluate(f"window.scrollBy({delta}, 0)")
            else:
                delta = _SCROLL_DELTA if direction == "down" else -_SCROLL_DELTA
                self._page.evaluate(f"window.scrollBy(0, {delta})")
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            return self._fail(exc)
        return OpResult(True, detail={"page_ref": self._page_ref})

    def wait(self, condition: str, timeout_ms: int) -> OpResult:
        """等待条件满足（任务 4.3）。

        条件语法：``selector: <CSS>``（元素可见，默认）/ ``text: <文本>`` /
        ``url: <子串>``；未带前缀时按 selector 处理。超时返回 ok=False + TIMEOUT。
        """
        if not isinstance(timeout_ms, int) or timeout_ms <= 0:
            return OpResult(
                False,
                f"timeout_ms 必须为正整数: {timeout_ms}",
                {"code": ErrorCode.INVALID_ARGUMENT, "page_ref": self._page_ref},
            )
        cond_type, value = self._parse_condition(condition)
        if cond_type is None or not value:
            return OpResult(
                False,
                f"无法识别的等待条件: {condition}",
                {"code": ErrorCode.INVALID_ARGUMENT, "page_ref": self._page_ref},
            )
        deadline = time.monotonic() + timeout_ms / 1000.0
        try:
            while time.monotonic() < deadline:
                if self._check_condition(cond_type, value):
                    return OpResult(True, detail={"page_ref": self._page_ref})
                time.sleep(0.05)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            return self._fail(exc)
        return OpResult(
            False,
            f"等待条件未满足（{timeout_ms}ms）: {condition}",
            {"code": ErrorCode.TIMEOUT, "page_ref": self._page_ref},
        )

    @staticmethod
    def _parse_condition(condition: str) -> tuple[str | None, str]:
        for prefix in ("selector:", "text:", "url:"):
            if condition.startswith(prefix):
                return prefix[:-1], condition[len(prefix):].strip()
        return "selector", condition.strip()

    def _check_condition(self, cond_type: str, value: str) -> bool:
        if cond_type == "selector":
            return self._page.locator(value).is_visible()
        if cond_type == "text":
            return self._page.get_by_text(value, exact=False).count() > 0
        return value in self._page.url

    # ------------------------------------------------------------------ 文件

    def download(self, ref: ElementRef, save_dir: str) -> OpResult:
        """触发下载并保存到 ``save_dir``（任务 5.1）。"""
        try:
            os.makedirs(save_dir, exist_ok=True)
        except OSError as exc:
            return OpResult(False, f"保存目录不可用: {exc}", {"code": ErrorCode.DOWNLOAD_FAILED})
        try:
            with self._page.expect_download(timeout=self._timeout_ms) as download_info:
                self._locator(ref).click(timeout=self._timeout_ms)
            download = download_info.value
            filename = download.suggested_filename or "download"
            dest = os.path.join(save_dir, filename)
            download.save_as(dest)
        except PlaywrightTimeoutError as exc:
            if "waiting for download" in str(exc).lower():
                return OpResult(
                    False,
                    str(exc),
                    {"code": ErrorCode.DOWNLOAD_FAILED, "page_ref": self._page_ref},
                )
            return self._fail(exc)
        except PlaywrightError as exc:
            return self._fail(exc)
        except OSError as exc:
            return OpResult(
                False,
                f"下载保存失败: {exc}",
                {"code": ErrorCode.DOWNLOAD_FAILED, "page_ref": self._page_ref},
            )
        return OpResult(
            True,
            detail={"path": dest, "filename": filename, "page_ref": self._page_ref},
        )

    def upload(self, ref: ElementRef, file_path: str) -> OpResult:
        """向文件选择控件写入文件（任务 5.2）。"""
        if not os.path.isfile(file_path):
            return OpResult(
                False,
                f"待上传文件不存在: {file_path}",
                {"code": ErrorCode.INVALID_ARGUMENT, "page_ref": self._page_ref},
            )
        try:
            self._locator(ref).set_input_files(file_path)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            code, message = _classify_playwright_error(exc)
            if code == "FATAL":
                raise FatalBrowserError(f"浏览器致命错误: {message}") from exc
            return OpResult(
                False,
                message,
                {"code": ErrorCode.UPLOAD_FAILED, "page_ref": self._page_ref},
            )
        return OpResult(True, detail={"file": file_path, "page_ref": self._page_ref})

    # ------------------------------------------------------------------ 截图

    def screenshot(self, path: str) -> OpResult:
        """保存当前页面状态为 PNG（任务 7.1，成功时 ``detail["path"]``）。"""
        if not isinstance(path, str) or not path:
            return OpResult(
                False,
                "截图路径不能为空",
                {"code": ErrorCode.INVALID_ARGUMENT, "page_ref": self._page_ref},
            )
        final_path = path
        screenshot_dir = self._driver._config.screenshot_dir if self._driver._config else None
        if not os.path.isabs(path) and screenshot_dir:
            final_path = os.path.join(screenshot_dir, path)
        try:
            parent = os.path.dirname(os.path.abspath(final_path))
            os.makedirs(parent, exist_ok=True)
            self._page.screenshot(path=final_path, type="png")
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            return self._fail(exc)
        except OSError as exc:
            return OpResult(
                False,
                f"截图保存失败: {exc}",
                {"code": ErrorCode.UNKNOWN, "page_ref": self._page_ref},
            )
        return OpResult(True, detail={"path": final_path, "page_ref": self._page_ref})

    # ------------------------------------------------------------------ 页面管理

    def close(self) -> OpResult:
        """关闭该页面并使其引用失效（任务 3.2 相关）。"""
        try:
            self._page.close()
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            code, message = _classify_playwright_error(exc)
            if code == "FATAL":
                raise FatalBrowserError(f"浏览器致命错误: {message}") from exc
        self._driver._pages.pop(self._page_ref.id, None)
        return OpResult(True, detail={"page_ref": self._page_ref})
