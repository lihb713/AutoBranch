"""M1 任务 6.1/6.2：HTTP 监听（形态A）与独立请求（形态B）（真实浏览器集成测试）。"""

from __future__ import annotations

import json

import pytest

from autobranch.browser import ElementRef, ErrorCode, http_request

pytestmark = pytest.mark.integration


class TestHttpRecorderIntegration:
    """形态A：监听页面请求，clear/get_response（任务 6.1，验收标准 §6 第4条）。"""

    def _trigger_api_call(self, handle) -> None:
        assert handle.click(ElementRef("#call-api")).ok
        assert handle.wait("text: logintoken-123", 3000).ok

    def test_record_and_read_page_request(
        self, driver, server_url, open_page, page_handle
    ):
        ref = open_page(f"{server_url}/api_page.html")
        handle = page_handle(ref)
        driver.http_recorder.clear()
        self._trigger_api_call(handle)

        response = driver.http_recorder.get_response("POST", "/api/echo*")
        assert response is not None
        assert response.method == "POST"
        assert response.status == 200
        assert "/api/echo" in response.url
        payload = json.loads(response.body)
        assert payload["method"] == "POST"
        assert "logintoken" in payload["body"]

    def test_clear_makes_old_records_unreadable(
        self, driver, server_url, open_page, page_handle
    ):
        ref = open_page(f"{server_url}/api_page.html")
        handle = page_handle(ref)
        driver.http_recorder.clear()
        self._trigger_api_call(handle)
        assert driver.http_recorder.get_response("POST", "/api/echo*") is not None

        driver.http_recorder.clear()
        assert driver.http_recorder.get_response("POST", "/api/echo*") is None

    def test_no_match_returns_none(self, driver, server_url, open_page, page_handle):
        ref = open_page(f"{server_url}/api_page.html")
        handle = page_handle(ref)
        driver.http_recorder.clear()
        self._trigger_api_call(handle)
        assert driver.http_recorder.get_response("GET", "/api/echo*") is None
        assert driver.http_recorder.get_response("POST", "/api/nothing*") is None

    def test_records_persist_across_pages_in_session(
        self, driver, server_url, open_page, page_handle
    ):
        ref = open_page(f"{server_url}/api_page.html")
        handle = page_handle(ref)
        driver.http_recorder.clear()
        self._trigger_api_call(handle)
        # 新开页面，记录仍可读（会话级监听）
        ref2 = open_page(f"{server_url}/basic.html")
        handle2 = page_handle(ref2)
        assert handle2.url.endswith("/basic.html")
        assert driver.http_recorder.get_response("POST", "/api/echo*") is not None


class TestHttpRequestIntegration:
    """形态B：独立请求（任务 6.2，验收标准 §6 第5条）。"""

    def test_independent_request_returns_response(
        self, driver, server_url, open_page, page_handle
    ):
        ref = open_page(f"{server_url}/basic.html")
        handle = page_handle(ref)
        before_url = handle.url

        result = http_request(
            "GET",
            f"{server_url}/api/echo?tag=independent",
            headers={"X-Auth-Token": "t-123"},
        )
        assert result.ok
        response = result.detail["response"]
        assert response.status == 200
        payload = json.loads(response.body)
        assert payload["method"] == "GET"

        # 页面无任何加载/跳转行为
        assert handle.url == before_url

    def test_auth_headers_explicit_only(self, server_url, driver):
        result = http_request(
            "POST",
            f"{server_url}/api/echo?tag=auth",
            headers={"X-Auth-Token": "secret-token", "Content-Type": "application/json"},
            body=json.dumps({"hello": "world"}),
        )
        assert result.ok
        payload = json.loads(result.detail["response"].body)
        assert payload["headers"]["X-Auth-Token"] == "secret-token"
        # 不自动附加页面会话 cookie
        assert "Cookie" not in payload["headers"]
        assert json.loads(payload["body"]) == {"hello": "world"}

    def test_independent_request_no_page_cookies(self, driver, server_url, open_page, page_handle):
        # 页面会话里有 cookie（cookie_page.html 写入），独立请求仍不带
        open_page(f"{server_url}/cookie_page.html")
        result = http_request("GET", f"{server_url}/api/echo?tag=cookies")
        assert result.ok
        payload = json.loads(result.detail["response"].body)
        assert "Cookie" not in payload["headers"]

    def test_network_failure_returns_classified_result(self):
        result = http_request("GET", "http://127.0.0.1:1/nope", timeout_ms=3000)
        assert not result.ok
        assert result.detail["code"] == ErrorCode.NETWORK

    def test_invalid_arguments(self):
        assert not http_request("", "http://x/").ok
        assert not http_request("GET", "").ok
