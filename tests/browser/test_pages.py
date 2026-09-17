"""M1 任务 3.1/3.2/10.1：页面打开、页面引用绑定与多页隔离（真实浏览器集成测试）。"""

from __future__ import annotations

import pytest

from autobranch.browser import ElementRef, ErrorCode, PageRef

pytestmark = pytest.mark.integration


class TestOpenPage:
    """open 返回页面引用（任务 3.1）。"""

    def test_open_returns_ref_and_loads_url(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        assert handle.url.endswith("/basic.html")
        assert handle.title == "AutoBranch 基础操作测试页"

    def test_multiple_pages_coexist(self, driver, server_url, open_page, page_handle):
        ref_a = open_page(f"{server_url}/basic.html")
        ref_b = open_page(f"{server_url}/api_page.html")
        assert ref_a.id != ref_b.id
        handle_a = page_handle(ref_a)
        handle_b = page_handle(ref_b)
        assert handle_a.url.endswith("/basic.html")
        assert handle_b.url.endswith("/api_page.html")
        # 两页独立、均存活
        assert handle_a.title == "AutoBranch 基础操作测试页"
        assert handle_b.title == "AutoBranch API 监听测试页"

    def test_open_unreachable_returns_failure(self, driver):
        result = driver.open("http://127.0.0.1:1/unreachable", timeout_ms=3000)
        assert not result.ok
        assert result.detail["code"] in (ErrorCode.NETWORK, ErrorCode.LOAD_TIMEOUT)


class TestPageResolution:
    """按 PageRef 取回句柄，无效/已释放引用返回失败（任务 3.2）。"""

    def test_invalid_ref_returns_failure(self, driver):
        result = driver.page(PageRef("999"))
        assert not result.ok
        assert result.detail["code"] == ErrorCode.INVALID_REF

    def test_never_existed_ref_returns_failure(self, driver):
        result = driver.page(PageRef("not-existed"))
        assert not result.ok
        assert result.detail["code"] == ErrorCode.INVALID_REF

    def test_released_ref_returns_failure(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        assert handle.close().ok
        result = driver.page(ref)
        assert not result.ok
        assert result.detail["code"] == ErrorCode.INVALID_REF


class TestMultiTabIsolation:
    """多页/多标签操作互不串页、引用绑定正确（任务 10.1，验收标准 §6 第7条）。"""

    def test_operation_bound_to_specified_page(
        self, driver, server_url, open_page, page_handle
    ):
        ref_a = open_page(f"{server_url}/basic.html")
        ref_b = open_page(f"{server_url}/basic.html")
        handle_a = page_handle(ref_a)
        handle_b = page_handle(ref_b)

        result = handle_a.type(ElementRef("#username"), "alice")
        assert result.ok

        # 仅页面 A 被输入，页面 B 不受影响
        value_a = handle_a._page.evaluate("() => document.querySelector('#username').value")
        value_b = handle_b._page.evaluate("() => document.querySelector('#username').value")
        assert value_a == "alice"
        assert value_b == ""

        # 在页面 B 上点击，仅 B 的按钮行为被触发
        handle_b.click(ElementRef("#login-btn"))
        text_b = handle_b._page.evaluate(
            "() => document.getElementById('login-result-text').textContent"
        )
        text_a = handle_a._page.evaluate(
            "() => document.getElementById('login-result-text').textContent"
        )
        assert text_b == "点击已触发"
        assert text_a == "初始状态"

    def test_invalid_ref_does_not_affect_other_pages(
        self, driver, server_url, open_page, page_handle
    ):
        ref_a = open_page(f"{server_url}/basic.html")
        handle_a = page_handle(ref_a)
        bad_result = driver.page(PageRef("888"))
        assert not bad_result.ok
        # 页面 A 状态不受影响
        text = handle_a._page.evaluate(
            "() => document.getElementById('login-result-text').textContent"
        )
        assert text == "初始状态"

    def test_crawl_per_page_isolation(self, driver, server_url, open_page, page_handle):
        from autobranch.browser import DomProbe

        ref_a = open_page(f"{server_url}/basic.html")
        ref_b = open_page(f"{server_url}/api_page.html")
        probe = DomProbe(driver)
        snap_a = probe.crawl(ref_a)
        snap_b = probe.crawl(ref_b)
        assert snap_a.url.endswith("/basic.html")
        assert snap_b.url.endswith("/api_page.html")
        texts_a = " ".join(n.text for n in snap_a.elements)
        texts_b = " ".join(n.text for n in snap_b.elements)
        assert "欢迎回来" in texts_a
        assert "欢迎回来" not in texts_b
        assert "api-result" not in texts_a
