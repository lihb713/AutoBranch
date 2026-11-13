"""多标签页：新标签页注册、操作提示与切换（真实浏览器集成）。"""

from __future__ import annotations

import pytest

from autobranch.browser import ElementRef, PageRef

pytestmark = pytest.mark.integration


def test_click_target_blank_reports_and_switches_tab(driver, server_url, open_page, page_handle):
    ref = open_page(f"{server_url}/new_tab.html")
    handle = page_handle(ref)
    pre_ids = set(driver._pages)

    result = handle.click(ElementRef("#blank-link"))
    assert result.ok
    new_tabs = (result.detail or {}).get("new_tabs") or []
    assert new_tabs, f"未检测到新标签页: {result.detail}"
    new_id = str(new_tabs[0]["id"])
    assert new_id not in pre_ids

    tabs = driver.list_tabs()
    assert any(tab["id"] == new_id for tab in tabs)
    assert any(tab["active"] for tab in tabs)

    switched = driver.activate_page(PageRef(id=new_id))
    assert switched.ok
    new_handle = page_handle(PageRef(id=new_id))
    assert new_handle.url.endswith("/basic.html")


def test_window_open_reports_new_tab(driver, server_url, open_page, page_handle):
    ref = open_page(f"{server_url}/new_tab.html")
    handle = page_handle(ref)
    result = handle.click(ElementRef("#popup-btn"))
    assert result.ok
    assert (result.detail or {}).get("new_tabs")
