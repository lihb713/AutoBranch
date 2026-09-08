"""M1 任务 9.1/9.2：程序侧失败分类与致命错误识别（真实浏览器集成测试）。"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from webops.browser import (
    ElementRef,
    ErrorCode,
    FatalBrowserError,
    OpResult,
)
from webops.browser.driver import _classify_playwright_error

pytestmark = pytest.mark.integration


class TestProgrammaticClassificationUnit:
    """分类映射的纯逻辑（任务 9.1，验收标准 §6 结合 §9.4）。"""

    def test_fatal_keywords(self):
        for message in (
            "Target page, context or browser has been closed",
            "Browser has been closed",
            "Execution context was destroyed",
            "Connection is closed",
        ):
            code, _ = _classify_playwright_error(PlaywrightTimeoutError(message))
            assert code == "FATAL", message

    def test_timeout_without_resolved_element(self):
        message = "Timeout 3000ms exceeded.\nwaiting for locator('button#x')"
        code, _ = _classify_playwright_error(PlaywrightTimeoutError(message))
        assert code == ErrorCode.NOT_FOUND

    def test_timeout_with_hidden_element(self):
        message = (
            "Timeout 3000ms exceeded.\nwaiting for element to be visible\n"
            "locator resolved to <button id='x'>\nelement is hidden"
        )
        code, _ = _classify_playwright_error(PlaywrightTimeoutError(message))
        assert code == ErrorCode.NOT_VISIBLE

    def test_timeout_with_disabled_element(self):
        message = "locator resolved to <input>\nelement is disabled"
        code, _ = _classify_playwright_error(PlaywrightTimeoutError(message))
        assert code == ErrorCode.NOT_ENABLED

    def test_unknown_fallback(self):
        code, _ = _classify_playwright_error(ValueError("something odd"))
        assert code == ErrorCode.UNKNOWN


class TestOperationReturnShapes:
    """每次操作返回统一 OpResult 且携带分类信息（任务 9.1）。"""

    def test_operation_result_shape(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.click(ElementRef("#login-btn"))
        assert isinstance(result, OpResult)
        assert result.ok is True
        assert result.error is None

    def test_failure_carries_code_and_message(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.click(ElementRef("#nope"))
        assert isinstance(result, OpResult)
        assert result.ok is False
        assert result.error is not None
        assert result.detail["code"] == ErrorCode.NOT_FOUND

    def test_wait_timeout_is_classified(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.wait("selector: #ghost", 300)
        assert result.ok is False
        assert result.detail["code"] == ErrorCode.TIMEOUT


class TestFatalErrors:
    """致命错误识别并中断流程（任务 9.2，验收标准 §6 第8条）。"""

    def test_browser_crash_raises_fatal(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        # 模拟浏览器崩溃：外部关闭浏览器进程
        driver._browser.close()
        with pytest.raises(FatalBrowserError):
            handle.click(ElementRef("#login-btn"))

    def test_operation_after_crash_on_other_page(
        self, driver, server_url, open_page, page_handle
    ):
        ref_a = open_page(f"{server_url}/basic.html")
        open_page(f"{server_url}/api_page.html")
        handle_a = page_handle(ref_a)
        driver._browser.close()
        with pytest.raises(FatalBrowserError):
            handle_a.click(ElementRef("#login-btn"))

    def test_operation_after_stop_raises_fatal(
        self, driver, server_url, open_page, page_handle
    ):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        driver.stop()
        with pytest.raises(FatalBrowserError):
            handle.click(ElementRef("#login-btn"))

    def test_stop_after_crash_is_safe(self, driver, server_url, open_page):
        open_page(f"{server_url}/basic.html")
        driver._browser.close()
        driver.stop()  # 不应抛异常

    def test_start_after_crash_recovers(self, driver, server_url, open_page, page_handle):
        open_page(f"{server_url}/basic.html")
        driver._browser.close()
        driver.start()
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        assert handle.click(ElementRef("#login-btn")).ok
