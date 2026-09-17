"""浏览器插件真实浏览器集成测试（组 2.3）。

需真实浏览器（``pytest -m integration``）：验证 open → 语义图（截图）链路。
"""

from __future__ import annotations

import pytest
from autobranch.semantic_graph.llm_fill import MockFiller

from autobranch.browser import BrowserConfig, BrowserDriver
from autobranch.plugin_system import PluginRegistry, PluginRuntime
from autobranch.plugins.browser import BrowserPlugin

pytestmark = pytest.mark.integration

PAGE_HTML = """
<html><body>
  <h1>Hello AutoBranch</h1>
  <button id="ok">确定</button>
</body></html>
"""


@pytest.fixture
def driver():
    instance = BrowserDriver()
    instance.start(BrowserConfig(timeout_ms=5000))
    yield instance
    instance.stop()


@pytest.fixture
def registry(driver, tmp_path):
    reg = PluginRegistry()
    reg.register(BrowserPlugin())
    runtime = PluginRuntime(
        browser_factory=lambda: driver,
        llm_filler=MockFiller(),
        screenshot_dir=str(tmp_path / "shots"),
    )
    reg.ensure_loaded("browser", runtime)
    return reg


def test_open_returns_page_object(registry):
    result = registry.call("browser.open", {"url": "data:text/html," + PAGE_HTML})
    assert result.ok, result.error
    page = result.value
    assert "PageObject" in str(page)


def test_get_url_after_open(registry):
    registry.call("browser.open", {"url": "data:text/html," + PAGE_HTML})
    result = registry.call("browser.get_url")
    assert result.ok
    assert "data:text/html" in str(result.value)


def test_semantic_graph_generates_text(registry):
    registry.call("browser.open", {"url": "data:text/html," + PAGE_HTML})
    result = registry.call("browser.semantic_graph", {"scope": "full", "lod": 2})
    assert result.ok, result.error
    assert result.detail.get("text") is not None


def test_release_stops_browser(registry, driver):
    registry.call("browser.open", {"url": "data:text/html," + PAGE_HTML})
    registry.release()
    assert not registry.is_loaded("browser")
