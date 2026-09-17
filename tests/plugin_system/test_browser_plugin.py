"""浏览器插件（M7）测试：注册 / 页面对象 / 懒装配 / 加载器排除 common。"""

from __future__ import annotations

import sys
import types

from autobranch.browser.models import OpResult, PageRef

from autobranch.plugin_system import PluginRegistry, load_builtin_plugins
from autobranch.plugins.browser import BrowserPlugin
from autobranch.schema.models import PageRef as SchemaPageRef  # noqa: F401


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url

    def scroll(self, direction):
        return OpResult(True, detail={"direction": direction})

    def wait(self, condition, timeout):
        return OpResult(True, detail={})

    def screenshot(self, path):
        return OpResult(True, detail={"path": path})


class FakeBrowser:
    def __init__(self) -> None:
        self.opened: list[str] = []
        self.stopped = False
        self.pages: dict[str, FakePage] = {}

    def open(self, url):
        self.opened.append(url)
        self.pages["p1"] = FakePage(url)
        return OpResult(True, detail={"page_ref": PageRef(id="p1"), "url": url})

    def activate_page(self, ref):
        return OpResult(True, detail={})

    def page(self, ref):
        page = self.pages.get(ref.id)
        if page is None:
            return OpResult(False, "页面不存在", {"code": "NOT_FOUND"})
        return OpResult(True, detail={"page": page})

    def stop(self):
        self.stopped = True

    @property
    def http_recorder(self):
        return self

    def clear(self):
        pass

    def get_response(self, method, url_pattern):
        return None


def _make_ready(browser) -> tuple[PluginRegistry, BrowserPlugin]:
    """注册浏览器插件并以 mock 浏览器工厂装配（经 ensure_loaded 触发懒装配）。"""
    reg = PluginRegistry()
    plugin = BrowserPlugin()
    runtime = types.SimpleNamespace(browser_factory=lambda: browser)
    reg.register(plugin)
    reg.ensure_loaded("browser", runtime)
    return reg, plugin


def test_register_browser_plugin_exposes_functions():
    reg = PluginRegistry()
    plugin = BrowserPlugin()
    reg.register(plugin)
    names = set(reg.functions())
    assert {
        "browser.open",
        "browser.activate",
        "browser.extract",
        "browser.semantic_graph",
        "browser.click",
        "browser.type",
    } <= names
    assert reg.function("browser.extract").is_producing  # output_param target
    assert reg.function("browser.open").returns == ("page",)


def test_open_returns_page_object():
    browser = FakeBrowser()
    reg, _ = _make_ready(browser)
    result = reg.call("browser.open", {"url": "https://example.com"})
    assert result.ok
    page = result.value
    assert page.url == "https://example.com"
    assert "PageObject" in str(page)


def test_get_url_after_open():
    browser = FakeBrowser()
    reg, _ = _make_ready(browser)
    reg.call("browser.open", {"url": "https://a.com"})
    result = reg.call("browser.get_url")
    assert result.ok and result.value == "https://a.com"


def test_activate_with_page_object():
    browser = FakeBrowser()
    reg, _ = _make_ready(browser)
    opened = reg.call("browser.open", {"url": "https://a.com"})
    result = reg.call("browser.activate", {"page": opened.value})
    assert result.ok


def test_release_stops_browser():
    browser = FakeBrowser()
    reg, _ = _make_ready(browser)
    reg.call("browser.open", {"url": "https://a.com"})
    reg.release()
    assert browser.stopped
    assert not reg.is_loaded("browser")


def test_scroll_without_page_fails():
    reg, _ = _make_ready(FakeBrowser())
    result = reg.call("browser.scroll", {"direction": "down"})
    assert not result.ok


def test_loader_scans_plugins_excluding_common():
    reg = PluginRegistry()
    sys.path.insert(0, ".")
    try:
        loaded = load_builtin_plugins(reg, "autobranch/plugins")
    finally:
        if "." in sys.path:
            sys.path.remove(".")
    assert "browser" in loaded
    assert "common" not in loaded
    assert set(reg.functions()) >= {"browser.open", "browser.extract", "browser.semantic_graph"}
