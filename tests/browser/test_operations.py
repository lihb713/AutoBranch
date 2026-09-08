"""M1 任务 4.1~4.4：页面操作函数与程序侧失败分类（真实浏览器集成测试）。"""

from __future__ import annotations

import pytest

from webops.browser import ElementRef, ErrorCode

pytestmark = pytest.mark.integration


def _text(handle, selector: str) -> str:
    return handle._page.evaluate(
        f"() => document.querySelector('{selector}').textContent"
    )


def _value(handle, selector: str) -> str:
    return handle._page.evaluate(f"() => document.querySelector('{selector}').value")


def _checked(handle, selector: str) -> bool:
    return handle._page.evaluate(f"() => document.querySelector('{selector}').checked")


class TestClickAndType:
    """click / type（任务 4.1，验收标准 §6 第2条）。"""

    def test_click_triggers_behavior(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.click(ElementRef("#login-btn"))
        assert result.ok
        assert _text(handle, "#login-result-text") == "点击已触发"

    def test_type_updates_value(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.type(ElementRef("#username"), "admin")
        assert result.ok
        assert _value(handle, "#username") == "admin"

    def test_click_after_type_flow(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        handle.type(ElementRef("#username"), "alice")
        handle.click(ElementRef("#login-btn"))
        assert _text(handle, "#login-result") == "登录成功-alice"

    def test_type_replaces_previous_value(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        handle.type(ElementRef("#username"), "first")
        handle.type(ElementRef("#username"), "second")
        assert _value(handle, "#username") == "second"


class TestSelectCheckUncheck:
    """select / check / uncheck（任务 4.2）。"""

    def test_select_by_label(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.select(ElementRef("#role"), "普通用户")
        assert result.ok
        assert _value(handle, "#role") == "user"

    def test_select_by_value(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.select(ElementRef("#role"), "guest")
        assert result.ok
        assert _value(handle, "#role") == "guest"

    def test_check_and_uncheck(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        assert handle.check(ElementRef("#remember")).ok
        assert _checked(handle, "#remember") is True
        assert handle.uncheck(ElementRef("#remember")).ok
        assert _checked(handle, "#remember") is False


class TestScrollAndWait:
    """scroll / wait（任务 4.3）。"""

    def test_scroll_down_changes_position(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        assert handle.scroll("down").ok
        assert handle._page.evaluate("() => window.scrollY") > 0

    def test_scroll_top_resets(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        handle.scroll("down")
        assert handle.scroll("top").ok
        assert handle._page.evaluate("() => window.scrollY") == 0

    def test_scroll_invalid_direction(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.scroll("sideways")
        assert not result.ok
        assert result.detail["code"] == ErrorCode.INVALID_ARGUMENT

    def test_wait_selector_success(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.wait("selector: #late-element", 3000)
        assert result.ok

    def test_wait_text_success(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.wait("text: 延迟出现的文本", 3000)
        assert result.ok

    def test_wait_timeout_returns_failure(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.wait("selector: #never-exists", 400)
        assert not result.ok
        assert result.detail["code"] == ErrorCode.TIMEOUT

    def test_wait_invalid_timeout(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.wait("selector: #late-element", -1)
        assert not result.ok
        assert result.detail["code"] == ErrorCode.INVALID_ARGUMENT


class TestOperationFailures:
    """元素操作失败分类（任务 4.4，验收标准 §6 结合 §9.4）。"""

    def test_click_missing_element(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.click(ElementRef("#does-not-exist"))
        assert not result.ok
        assert result.detail["code"] == ErrorCode.NOT_FOUND

    def test_click_hidden_element(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.click(ElementRef("#always-hidden"))
        assert not result.ok
        assert result.detail["code"] == ErrorCode.NOT_VISIBLE

    def test_click_disabled_element(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.click(ElementRef("#disabled-btn"))
        assert not result.ok
        assert result.detail["code"] == ErrorCode.NOT_ENABLED

    def test_click_covered_element(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.click(ElementRef("#covered-btn"))
        assert not result.ok
        assert result.detail["code"] == ErrorCode.NOT_INTERACTABLE

    def test_type_on_missing_element(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.type(ElementRef("#missing-input"), "x")
        assert not result.ok
        assert result.detail["code"] == ErrorCode.NOT_FOUND

    def test_failure_does_not_change_page_state(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        handle.click(ElementRef("#does-not-exist"))
        assert _text(handle, "#login-result-text") == "初始状态"
