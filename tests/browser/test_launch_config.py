"""浏览器启动参数单测（channel / executable_path，无真实浏览器）。

验证 ``BrowserDriver._launch_kwargs``：默认用自带浏览器；channel 用系统发行版；
executable_path 优先于 channel；可叠加额外 args（如直连的 --no-proxy-server）。
"""

from __future__ import annotations

from autobranch.plugins.browser.driver.config import BrowserConfig
from autobranch.plugins.browser.driver.driver import BrowserDriver


def _driver(cfg: BrowserConfig) -> BrowserDriver:
    driver = BrowserDriver()
    driver._config = cfg  # 单测注入配置（无需真正 start）
    return driver


def test_launch_kwargs_default_uses_bundled():
    assert _driver(BrowserConfig())._launch_kwargs() == {"headless": True}


def test_launch_kwargs_channel():
    assert _driver(BrowserConfig(channel="chrome"))._launch_kwargs() == {
        "headless": True,
        "channel": "chrome",
    }


def test_launch_kwargs_executable_path_priority_over_channel():
    kwargs = _driver(
        BrowserConfig(channel="chrome", executable_path="C:/Chrome/chrome.exe")
    )._launch_kwargs()
    assert kwargs["executable_path"] == "C:/Chrome/chrome.exe"
    assert "channel" not in kwargs


def test_launch_kwargs_extra_args():
    kwargs = _driver(BrowserConfig())._launch_kwargs(["--no-proxy-server"])
    assert kwargs["args"] == ["--no-proxy-server"]
