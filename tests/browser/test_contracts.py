"""M1 任务 1.2 + 6.1 匹配逻辑：数据契约与 HTTP 匹配纯逻辑单元测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import pytest
from autobranch.browser.http import HttpRecorder, url_matches

from autobranch.browser import (
    BrowserError,
    ElementRef,
    ErrorCode,
    FatalBrowserError,
    HttpResponse,
    LODSpec,
    OpResult,
    PageRef,
    PageRefError,
)


class TestOpResult:
    """OpResult 字段默认值与序列化行为。"""

    def test_defaults(self):
        result = OpResult(True)
        assert result.ok is True
        assert result.error is None
        assert result.detail is None

    def test_failure_fields(self):
        result = OpResult(False, "元素不存在", {"code": ErrorCode.NOT_FOUND})
        assert result.ok is False
        assert result.error == "元素不存在"
        assert result.detail["code"] == ErrorCode.NOT_FOUND

    def test_asdict_roundtrip(self):
        result = OpResult(True, detail={"page_ref": PageRef("1")})
        payload = asdict(result)
        assert payload["ok"] is True
        assert payload["detail"]["page_ref"] == {"id": "1"}


class TestReferences:
    """ElementRef / PageRef 引用契约。"""

    def test_element_ref(self):
        ref = ElementRef("button#login")
        assert ref.id == "button#login"

    def test_page_ref(self):
        ref = PageRef("3")
        assert ref.id == "3"

    def test_references_frozen(self):
        with pytest.raises(FrozenInstanceError):
            ElementRef("a").id = "b"  # type: ignore[misc]


class TestLODSpec:
    """LOD 四维参数（契约 §9.5）。"""

    def test_from_level_table(self):
        expected0 = LODSpec(depth=0, breadth="direct", attributes="minimal", relations="none")
        assert LODSpec.from_level(0) == expected0
        assert LODSpec.from_level(1).depth == 1
        assert LODSpec.from_level(2).depth == 2
        assert LODSpec.from_level(3).depth == -1

    def test_from_level_invalid(self):
        with pytest.raises(ValueError):
            LODSpec.from_level(9)


class TestExceptions:
    """可分类异常层级。"""

    def test_fatal_is_browser_error(self):
        assert issubclass(FatalBrowserError, BrowserError)
        assert issubclass(PageRefError, BrowserError)
        assert not issubclass(PageRefError, FatalBrowserError)

    def test_fatal_raise(self):
        with pytest.raises(FatalBrowserError):
            raise FatalBrowserError("浏览器崩溃")


class TestUrlMatches:
    """get_response 的 URL 模式匹配规则（设计 D5）。"""

    def test_substring_match(self):
        assert url_matches("/api/login", "http://host/api/login")
        assert url_matches("api/login", "http://host/api/login?x=1")

    def test_wildcard_match(self):
        assert url_matches("/api/*", "http://host/api/login")
        assert url_matches("/api/*", "http://host/api/orders/list")
        assert url_matches("*/files/*", "http://host/files/data.txt")

    def test_no_match(self):
        assert not url_matches("/api/login", "http://host/other/login")
        assert not url_matches("/api/*", "http://host/static/app.js")


class TestHttpRecorderLogic:
    """形态A 记录器纯逻辑：clear / get_response / 首个匹配。"""

    def _recorder_with(self, *responses: HttpResponse) -> HttpRecorder:
        recorder = HttpRecorder()
        recorder._records.extend(responses)
        return recorder

    def test_get_response_first_match(self):
        r1 = HttpResponse("GET", "http://host/api/a", 200, body="A")
        r2 = HttpResponse("GET", "http://host/api/b", 200, body="B")
        recorder = self._recorder_with(r1, r2)
        assert recorder.get_response("GET", "/api/a") is r1
        assert recorder.get_response("GET", "/api/*") is r1

    def test_method_case_insensitive(self):
        recorder = self._recorder_with(HttpResponse("get", "http://host/api/a", 200))
        assert recorder.get_response("GET", "/api/a") is not None

    def test_no_match_returns_none(self):
        recorder = self._recorder_with(HttpResponse("POST", "http://host/api/a", 200))
        assert recorder.get_response("POST", "/api/nope") is None
        assert recorder.get_response("GET", "/api/a") is None

    def test_clear_empties(self):
        recorder = self._recorder_with(HttpResponse("GET", "http://host/api/a", 200))
        recorder.clear()
        assert recorder.get_response("GET", "/api/a") is None
