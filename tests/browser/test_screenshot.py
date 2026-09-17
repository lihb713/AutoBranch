"""M1 任务 7.1：页面截图（真实浏览器集成测试，验收标准 §6 第6条）。"""

from __future__ import annotations

import os
import struct

import pytest

from autobranch.browser import BrowserConfig, BrowserDriver

pytestmark = pytest.mark.integration

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_size(path: str) -> tuple[int, int]:
    """读取 PNG IHDR 的宽高。"""
    with open(path, "rb") as f:
        data = f.read(24)
    assert data[:8] == PNG_SIGNATURE
    width, height = struct.unpack(">II", data[16:24])
    return width, height


class TestScreenshot:
    """保存当前页面状态 PNG 并返回路径。"""

    def test_screenshot_saved_as_png(self, driver, server_url, open_page, page_handle, tmp_path):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        path = str(tmp_path / "shot.png")
        result = handle.screenshot(path)
        assert result.ok
        saved = result.detail["path"]
        assert saved == path
        assert os.path.isfile(saved)
        with open(saved, "rb") as f:
            assert f.read(8) == PNG_SIGNATURE

    def test_screenshot_dimensions_match_viewport(
        self, driver, server_url, open_page, page_handle, tmp_path
    ):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        viewport = handle._page.viewport_size
        path = str(tmp_path / "shot2.png")
        assert handle.screenshot(path).ok
        width, height = _png_size(path)
        assert width == viewport["width"]
        assert height == viewport["height"]

    def test_screenshot_with_config_dir(self, server_url, tmp_path):
        config = BrowserConfig(timeout_ms=5000, screenshot_dir=str(tmp_path / "shots"))
        instance = BrowserDriver()
        instance.start(config)
        try:
            result = instance.open(f"{server_url}/basic.html")
            assert result.ok
            handle = instance.page(result.detail["page_ref"]).detail["page"]
            outcome = handle.screenshot("page.png")  # 相对路径拼接进 screenshot_dir
            assert outcome.ok
            assert outcome.detail["path"] == str(config.screenshot_dir + os.sep + "page.png")
            assert os.path.isfile(outcome.detail["path"])
        finally:
            instance.stop()

    def test_screenshot_empty_path(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        result = handle.screenshot("")
        assert not result.ok
