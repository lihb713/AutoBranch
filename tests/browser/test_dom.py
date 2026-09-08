"""M1 任务 8.1/8.2：DOM 爬取快照（真实浏览器集成测试，验收标准 §6 结合 §8.9）。"""

from __future__ import annotations

import pytest

from webops.browser import DomProbe, ElementRef, LODSpec, PageRef, PageRefError

pytestmark = pytest.mark.integration


def _by_dom_id(snapshot, dom_id):
    return next((n for n in snapshot.elements if n.dom_id == dom_id), None)


def _all_text(snapshot) -> str:
    return " ".join(n.text for n in snapshot.elements)


class TestCrawlStructure:
    """快照结构完整、字段取值正确（任务 8.1）。"""

    def test_snapshot_basic_fields(self, driver, server_url, open_page):
        ref = open_page(f"{server_url}/basic.html")
        snapshot = DomProbe(driver).crawl(ref)
        assert snapshot.url.endswith("/basic.html")
        assert snapshot.title == "WebOps 基础操作测试页"
        assert snapshot.root is not None
        assert snapshot.root.role == "document"
        assert len(snapshot.elements) > 0

    def test_roles_detected(self, driver, server_url, open_page):
        ref = open_page(f"{server_url}/basic.html")
        snapshot = DomProbe(driver).crawl(ref)
        roles = {n.role for n in snapshot.elements}
        for expected in ("button", "textbox", "listbox", "paragraph", "cell", "row", "table"):
            assert expected in roles, f"缺少 role: {expected}，实际: {roles}"

    def test_programmatic_values_read(self, driver, server_url, open_page):
        ref = open_page(f"{server_url}/basic.html")
        snapshot = DomProbe(driver).crawl(ref)
        username = _by_dom_id(snapshot, "username")
        assert username is not None
        assert username.role == "textbox"
        assert username.value == ""
        role_select = _by_dom_id(snapshot, "role")
        assert role_select.options == ["管理员", "普通用户", "访客"]
        assert role_select.selected == "管理员"

    def test_text_and_bounds(self, driver, server_url, open_page):
        ref = open_page(f"{server_url}/basic.html")
        snapshot = DomProbe(driver).crawl(ref)
        greeting = _by_dom_id(snapshot, "greeting")
        assert greeting is not None
        assert greeting.text == "欢迎回来，张三"
        login_btn = _by_dom_id(snapshot, "login-btn")
        assert login_btn is not None
        assert login_btn.bounds is not None
        assert login_btn.bounds.w > 0
        assert login_btn.bounds.h > 0

    def test_tree_hierarchy(self, driver, server_url, open_page):
        ref = open_page(f"{server_url}/basic.html")
        snapshot = DomProbe(driver).crawl(ref)
        # 表单为容器，用户名输入框为其后代
        form = _by_dom_id(snapshot, "login-form")
        assert form is not None
        assert form.role == "form"
        assert any(c.dom_id == "username" for c in form.children)

    def test_invalid_ref_raises(self, driver):
        with pytest.raises(PageRefError):
            DomProbe(driver).crawl(PageRef("missing"))


class TestCrawlFiltering:
    """筛选与边界规则（任务 8.2）：隐藏/零尺寸/aria-hidden 剔除、iframe 不合并。"""

    def _snapshot(self, driver, server_url, open_page, page: str):
        ref = open_page(f"{server_url}/{page}")
        return DomProbe(driver).crawl(ref)

    def test_hidden_and_aria_hidden_excluded(self, driver, server_url, open_page):
        snapshot = self._snapshot(driver, server_url, open_page, "dom_filter.html")
        texts = _all_text(snapshot)
        assert "display:none 内的文本" not in texts
        assert "aria-hidden 内的文本" not in texts
        assert _by_dom_id(snapshot, "display-none-child") is None
        assert _by_dom_id(snapshot, "aria-hidden-box") is None

    def test_zero_size_excluded(self, driver, server_url, open_page):
        snapshot = self._snapshot(driver, server_url, open_page, "dom_filter.html")
        assert _by_dom_id(snapshot, "zero-size") is None

    def test_hidden_input_excluded(self, driver, server_url, open_page):
        snapshot = self._snapshot(driver, server_url, open_page, "dom_filter.html")
        assert _by_dom_id(snapshot, "hidden-input") is None

    def test_iframe_content_not_merged(self, driver, server_url, open_page):
        snapshot = self._snapshot(driver, server_url, open_page, "dom_filter.html")
        texts = _all_text(snapshot)
        assert "iframe 内部内容" not in texts
        assert _by_dom_id(snapshot, "iframe-btn") is None

    def test_visible_elements_kept(self, driver, server_url, open_page):
        snapshot = self._snapshot(driver, server_url, open_page, "dom_filter.html")
        assert _by_dom_id(snapshot, "keep-me") is not None
        assert "可见文本" in _all_text(snapshot)


class TestProgrammaticValueFresh:
    """程序化值实时读取（任务 8.2，验收标准 §6 结合 §9.5）。"""

    def test_value_reflects_latest_state(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/dom_filter.html")
        probe = DomProbe(driver)

        before = probe.crawl(ref)
        assert _by_dom_id(before, "dynamic-value").value == "初始值"

        handle = page_handle(ref)
        assert handle.type(ElementRef("#dynamic-value"), "已修改的值").ok

        after = probe.crawl(ref)
        assert _by_dom_id(after, "dynamic-value").value == "已修改的值"


class TestLODDepth:
    """LOD 深度维度控制语义容器嵌套（契约 §9.5）。"""

    def test_lod0_shallower_than_lod3(self, driver, server_url, open_page):
        ref = open_page(f"{server_url}/basic.html")
        probe = DomProbe(driver)
        lod0 = probe.crawl(ref, LODSpec.from_level(0))
        lod3 = probe.crawl(ref, LODSpec.from_level(3))
        assert len(lod0.elements) < len(lod3.elements)
        # LOD-3 含深层嵌套元素（表格单元格），LOD-0 不含
        assert any(n.role == "cell" for n in lod3.elements)
        assert not any(n.role == "cell" for n in lod0.elements)

    def test_lod_recorded_in_snapshot(self, driver, server_url, open_page):
        ref = open_page(f"{server_url}/basic.html")
        snapshot = DomProbe(driver).crawl(ref, LODSpec.from_level(2))
        assert snapshot.lod.depth == 2
