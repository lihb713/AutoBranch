"""M1 浏览器驱动测试共享 fixture（本地 HTTP 测试服务器 + 浏览器驱动）。"""

from __future__ import annotations

import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from webops.browser import BrowserConfig, BrowserDriver

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


class _Handler(SimpleHTTPRequestHandler):
    """本地测试服务器：静态 fixture + 模拟 API 端点（/api/* 回显、/files/* 下载）。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FIXTURES_DIR, **kwargs)

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/files/data.txt"):
            data = b"hello-webops-download"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Disposition", 'attachment; filename="data.txt"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path.startswith("/api/"):
            self._json({"method": "GET", "path": self.path, "headers": dict(self.headers)})
            return
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            self._json(
                {"method": "POST", "path": self.path, "headers": dict(self.headers), "body": raw}
            )
            return
        return super().do_POST()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def http_server() -> str:
    """返回本地测试服务器 server_url（会话级，端口随机）。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def server_url(http_server: str) -> str:
    return http_server


@pytest.fixture
def driver() -> BrowserDriver:
    """全新浏览器会话（每次测试独立，冷启动语义）。"""
    instance = BrowserDriver()
    instance.start(BrowserConfig(timeout_ms=5000))
    yield instance
    instance.stop()


@pytest.fixture
def open_page(driver: BrowserDriver):
    """打开页面并断言成功，返回 PageRef。"""
    def _open(url: str):
        result = driver.open(url)
        assert result.ok, result.error
        return result.detail["page_ref"]
    return _open


@pytest.fixture
def page_handle(driver: BrowserDriver):
    """按 PageRef 取回页面句柄并断言成功。"""
    def _handle(page_ref):
        result = driver.page(page_ref)
        assert result.ok, result.error
        return result.detail["page"]
    return _handle
