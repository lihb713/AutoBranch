"""M4 语义图生成测试共享 fixture（集成测试复用 M1 本地 HTTP 服务器 + 浏览器驱动）。"""

from __future__ import annotations

import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from webops.browser import BrowserConfig, BrowserDriver
from webops.semantic_graph import MockFiller

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures"
)


class _Handler(SimpleHTTPRequestHandler):
    """本地测试服务器：提供静态 fixture（端口随机，独立于 M1 测试）。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FIXTURES_DIR, **kwargs)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def sg_http_server() -> str:
    """返回本地测试服务器 server_url（会话级，端口随机）。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def sg_driver() -> BrowserDriver:
    """全新浏览器会话（每次测试独立，冷启动语义）。"""
    instance = BrowserDriver()
    instance.start(BrowserConfig(timeout_ms=5000))
    yield instance
    instance.stop()


@pytest.fixture
def sg_open_page(sg_driver: BrowserDriver):
    """打开页面并断言成功，返回 PageRef。"""

    def _open(url: str):
        result = sg_driver.open(url)
        assert result.ok, result.error
        return result.detail["page_ref"]

    return _open


@pytest.fixture
def sg_page_handle(sg_driver: BrowserDriver):
    """按 PageRef 取回页面句柄并断言成功。"""

    def _handle(page_ref):
        result = sg_driver.page(page_ref)
        assert result.ok, result.error
        return result.detail["page"]

    return _handle


@pytest.fixture
def mock_filler() -> MockFiller:
    """默认 mock LLM 填充器（purpose=role，无关联边）。"""
    return MockFiller()
