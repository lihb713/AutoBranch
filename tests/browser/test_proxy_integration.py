"""浏览器代理路由集成测试（browser-proxy-routing 任务 2.2/2.3/3.1）。

关键约束：Playwright 设置代理时强制 ``<-loopback>`` 绕过，回环地址（127.0.0.1）
不会被代理。故用**本机非回环 IP** 作为页面目标 + 本地"记录代理"验证真实转发。
"""

from __future__ import annotations

import http.client
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest

from autobranch.browser import BrowserConfig, BrowserDriver

pytestmark = pytest.mark.integration


def _lan_ip() -> str:
    """取本机非回环 IPv4（经 UDP socket 连接公共地址学习本地地址，不发包）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


class _RecProxyHandler(BaseHTTPRequestHandler):
    """最小 HTTP 代理（仅 GET，无 CONNECT）：转发并记录请求目标。"""

    seen: list[str] = []

    def do_GET(self):
        url = self.path  # 代理请求目标为绝对 URI
        _RecProxyHandler.seen.append(url)
        parsed = urlparse(url)
        try:
            conn = http.client.HTTPConnection(parsed.netloc, timeout=10)
            conn.request("GET", parsed.path or "/")
            resp = conn.getresponse()
            body = resp.read()
            conn.close()
            self.send_response(resp.status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001 - 转发失败返回 502
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()
            msg = f"proxy forward failed: {exc}".encode()
            self.wfile.write(msg)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def lan_server() -> str:
    """绑定 0.0.0.0 的本地 HTTP 服务器，返回经本机非回环 IP 可达的 URL。"""
    server = ThreadingHTTPServer(
        ("0.0.0.0", 0),
        type("_H", (BaseHTTPRequestHandler,), {"log_message": lambda self, *a: None}),
    )
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://{_lan_ip()}:{port}/basic.html"
    yield url
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="module")
def rec_proxy() -> int:
    """本地记录代理，返回端口；记录转发目标到 ``seen``。"""
    _RecProxyHandler.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecProxyHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()
    server.server_close()


def test_custom_proxy_routing_forwards_through_recorder(lan_server, rec_proxy):
    """规则命中 → 经自定义代理转发（记录代理收到请求）。"""
    host = urlparse(lan_server).hostname
    cfg = {
        "default": "system",
        "profiles": {"记录代理": {"server": f"http://127.0.0.1:{rec_proxy}"}},
        "rules": [{"pattern": host, "proxy": "记录代理"}],
    }
    driver = BrowserDriver()
    try:
        driver.start(BrowserConfig(timeout_ms=10000), proxy_config=cfg)
        result = driver.open(lan_server)
        assert result.ok, result.error
        # 页面正常加载（代理转发成功）
        page = driver.page(result.detail["page_ref"])
        assert page.ok, page.error
        assert page.detail["page"].url == lan_server
        # 记录代理确实收到了该请求
        assert any(lan_server in u for u in _RecProxyHandler.seen), _RecProxyHandler.seen
    finally:
        driver.stop()


def test_direct_routing_accepts_direct_protocol(lan_server):
    """direct 模式：``proxy.server="direct://"`` 被接受，页面正常加载。"""
    host = urlparse(lan_server).hostname
    cfg = {
        "default": "system",
        "profiles": {"直连": {"mode": "direct"}},
        "rules": [{"pattern": host, "proxy": "直连"}],
    }
    driver = BrowserDriver()
    try:
        driver.start(BrowserConfig(timeout_ms=10000), proxy_config=cfg)
        result = driver.open(lan_server)
        assert result.ok, result.error
        page = driver.page(result.detail["page_ref"])
        assert page.ok and page.detail["page"].url == lan_server
    finally:
        driver.stop()


def test_same_proxy_shared_context(lan_server, rec_proxy):
    """同一代理模式多页面共享同一 context（cookie/会话共享）。"""
    host = urlparse(lan_server).hostname
    cfg = {
        "default": "system",
        "profiles": {"记录代理": {"server": f"http://127.0.0.1:{rec_proxy}"}},
        "rules": [{"pattern": host, "proxy": "记录代理"}],
    }
    driver = BrowserDriver()
    try:
        driver.start(BrowserConfig(timeout_ms=10000), proxy_config=cfg)
        r1 = driver.open(lan_server)
        r2 = driver.open(lan_server)
        assert r1.ok and r2.ok
        assert len(driver._contexts) == 1  # 同一代理 → 单一 context
    finally:
        driver.stop()


def test_no_config_keeps_default(lan_server):
    """无代理配置 → 不启用路由，页面正常打开（现状兼容）。"""
    driver = BrowserDriver()
    try:
        driver.start(BrowserConfig(timeout_ms=10000))
        result = driver.open(lan_server)
        assert result.ok, result.error
    finally:
        driver.stop()


def test_ignore_https_errors_still_works_with_proxy(lan_server, rec_proxy):
    """证书豁免与代理路由并存（context 参数同时含 proxy 与 ignore_https_errors）。"""
    host = urlparse(lan_server).hostname
    cfg = {
        "default": "system",
        "profiles": {"记录代理": {"server": f"http://127.0.0.1:{rec_proxy}"}},
        "rules": [{"pattern": host, "proxy": "记录代理"}],
    }
    driver = BrowserDriver()
    try:
        driver.start(BrowserConfig(timeout_ms=10000, ignore_https_errors=True), proxy_config=cfg)
        result = driver.open(lan_server)
        assert result.ok, result.error
    finally:
        driver.stop()
