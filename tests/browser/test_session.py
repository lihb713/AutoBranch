"""M1 任务 2.1/2.2：会话生命周期与冷启动（真实浏览器集成测试）。"""

from __future__ import annotations

import pytest

from autobranch.browser import ErrorCode

pytestmark = pytest.mark.integration


class TestSessionLifecycle:
    """start / stop 生命周期（任务 2.1）。"""

    def test_start_then_open_page(self, driver, server_url, open_page, page_handle):
        assert driver.running
        page_ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(page_ref)
        assert handle.url.endswith("/basic.html")

    def test_stop_releases_context_and_pages(self, driver, server_url, open_page):
        page_ref = open_page(f"{server_url}/basic.html")
        assert driver.running
        driver.stop()
        assert not driver.running
        result = driver.page(page_ref)
        assert not result.ok
        assert result.detail["code"] == ErrorCode.SESSION_NOT_RUNNING

    def test_stop_is_idempotent(self, driver):
        driver.stop()
        driver.stop()

    def test_open_without_start(self, server_url):
        from autobranch.browser import BrowserDriver

        fresh = BrowserDriver()
        result = fresh.open(f"{server_url}/basic.html")
        assert not result.ok
        assert result.detail["code"] == ErrorCode.SESSION_NOT_RUNNING

    def test_start_with_ignore_https_errors(self, server_url):
        """证书豁免开启后会话可正常打开页面（Playwright 接受该 context 参数）。"""
        from autobranch.browser import BrowserConfig, BrowserDriver

        instance = BrowserDriver()
        try:
            instance.start(BrowserConfig(timeout_ms=5000, ignore_https_errors=True))
            assert instance.running
            result = instance.open(f"{server_url}/basic.html")
            assert result.ok, result.error
        finally:
            instance.stop()


class TestColdStart:
    """每次 start 均为冷启动（任务 2.2，验收标准 §6 第1条）。"""

    def _read_cookie_and_storage(self, handle) -> tuple[str, str | None]:
        cookie = handle._page.evaluate("() => document.cookie")
        storage = handle._page.evaluate("() => localStorage.getItem('autobranch_test_key')")
        return cookie, storage

    def test_second_start_has_no_previous_state(
        self, driver, server_url, open_page, page_handle
    ):
        # 第一次会话：写入 cookie 与 localStorage
        ref1 = open_page(f"{server_url}/cookie_page.html")
        handle1 = page_handle(ref1)
        cookie1, storage1 = self._read_cookie_and_storage(handle1)
        assert "autobranch_test_cookie" in cookie1
        assert storage1 == "abc"

        # 重启会话（start 自动释放旧会话）
        driver.start()
        assert driver.running

        # 第二次会话：新 context，不应有任何残留。
        # 注意：不能再载入 cookie_page.html（它加载时会重新写入 cookie/localStorage），
        # 用不写状态的 basic.html 读取 document.cookie / localStorage。
        ref2 = open_page(f"{server_url}/basic.html")
        handle2 = page_handle(ref2)
        cookie2, storage2 = self._read_cookie_and_storage(handle2)
        assert "autobranch_test_cookie" not in cookie2
        assert storage2 is None

    def test_start_again_invalidates_old_ref(self, driver, server_url, open_page):
        ref1 = open_page(f"{server_url}/basic.html")
        driver.start()
        result = driver.page(ref1)
        assert not result.ok
        assert result.detail["code"] == ErrorCode.INVALID_REF

    def test_pages_share_one_context(self, driver, server_url, open_page, page_handle):
        ref_a = open_page(f"{server_url}/cookie_page.html")
        ref_b = open_page(f"{server_url}/basic.html")
        handle_a = page_handle(ref_a)
        assert "autobranch_test_cookie" in handle_a._page.evaluate("() => document.cookie")
        # 同 context 共享 cookie 空间：B 页也能读到 A 页写入的 cookie
        handle_b = page_handle(ref_b)
        cookie_b = handle_b._page.evaluate("() => document.cookie")
        assert "autobranch_test_cookie" in cookie_b
