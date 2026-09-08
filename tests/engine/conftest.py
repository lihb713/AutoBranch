"""M5 引擎函数层测试共享 fixture（本地静态服务器 + 浏览器驱动）。

真实浏览器辅助类（FakeBrowser/FakePageHandle/FakeProbe/快照构造器）位于
``tests/engine_helpers.py``，经 ``pythonpath=["tests"]`` 顶层导入。
"""

from __future__ import annotations

import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from webops.browser import BrowserConfig, BrowserDriver

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures"
)


class _Handler(SimpleHTTPRequestHandler):
    """本地测试服务器：提供静态 fixture（端口随机，独立于其他模块测试）。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FIXTURES_DIR, **kwargs)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def eng_http_server() -> str:
    """返回本地测试服务器 server_url（会话级，端口随机）。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def eng_driver() -> BrowserDriver:
    """全新浏览器会话（每次测试独立，冷启动语义）。"""
    instance = BrowserDriver()
    instance.start(BrowserConfig(timeout_ms=5000))
    yield instance
    instance.stop()
