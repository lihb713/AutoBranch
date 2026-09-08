"""M1 任务 5.1/5.2：download 与 upload 文件函数（真实浏览器集成测试）。"""

from __future__ import annotations

import os

import pytest

from webops.browser import ElementRef, ErrorCode

pytestmark = pytest.mark.integration


class TestDownload:
    """触发下载并保存文件（任务 5.1，验收标准 §6 第3条）。"""

    def test_download_saves_file(self, driver, server_url, open_page, page_handle, tmp_path):
        ref = open_page(f"{server_url}/download.html")
        handle = page_handle(ref)
        save_dir = str(tmp_path / "downloads")
        result = handle.download(ElementRef("#dl"), save_dir)
        assert result.ok
        path = result.detail["path"]
        assert os.path.isfile(path)
        with open(path, encoding="utf-8") as f:
            assert f.read() == "hello-webops-download"
        assert path.startswith(save_dir)


class TestUpload:
    """上传文件到控件（任务 5.2）。"""

    def test_upload_sets_file(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/upload.html")
        handle = page_handle(ref)
        source = os.path.join(os.path.dirname(__file__), "..", "fixtures", "upload.txt")
        result = handle.upload(ElementRef("#file"), os.path.abspath(source))
        assert result.ok
        name = handle._page.evaluate(
            "() => document.getElementById('file').files[0].name"
        )
        assert name == "upload.txt"
        assert _text(handle, "#file-name") == "upload.txt"

    def test_upload_nonexistent_file(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/upload.html")
        handle = page_handle(ref)
        result = handle.upload(ElementRef("#file"), "C:/nonexistent/ghost.txt")
        assert not result.ok
        assert result.detail["code"] == ErrorCode.INVALID_ARGUMENT


def _text(handle, selector: str) -> str:
    return handle._page.evaluate(f"() => document.querySelector('{selector}').textContent")
