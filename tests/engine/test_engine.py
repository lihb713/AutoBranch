"""M5 任务 4.x/5.x/6.1/6.2：页面绑定、各函数实现、错误语义。"""

from __future__ import annotations

import pytest
from engine_helpers import (
    FakeBrowser,
    FakePageHandle,
    FakeProbe,
    build_engine,
    fake_graph_generator,
    fake_response,
    make_graph,
    make_snapshot,
)

from webops.browser import ErrorCode, FatalBrowserError, OpResult, PageRef
from webops.engine import engine as engine_module
from webops.schema import PageRef as SchemaPageRef
from webops.semantic_graph.errors import LlmStageError, ProgramStageError


def _seeded(browser, url="http://example.com/page", value="", dom_id="username"):
    """打开页面 + 生成语义图（种子 ref 映射表）。"""
    engine, space, frame = build_engine(
        browser,
        probe=FakeProbe(),
        graph_generator=fake_graph_generator(
            make_graph(url=url, value=value), make_snapshot(url=url, value=value, dom_id=dom_id)
        ),
    )
    assert engine.call("open", {"url": url}).ok
    assert engine.call("semantic_graph", {"scope": "full", "lod": 2}).ok
    return engine, space, frame


class TestPageBinding:
    """任务 4.x：页面操作绑定当前页面变量。"""

    def test_no_current_page_variable_returns_failure(self):
        engine, _, _ = build_engine(FakeBrowser())
        result = engine.call("click", {"ref": "[1]"})
        assert result.ok is False
        assert "当前页面变量" in result.error

    def test_operations_bind_to_current_page(self):
        browser = FakeBrowser()
        engine, _, _ = _seeded(browser)
        handle = browser.pages["1"]

        assert engine.call("click", {"ref": "[1]"}).ok
        assert handle.calls[-1] == ("click", "#username")
        assert engine.call("type", {"ref": "[1]", "text": "x"}).ok
        assert handle.calls[-1] == ("type", "#username", "x")
        assert engine.call("select", {"ref": "[1]", "option": "A"}).ok
        assert handle.calls[-1] == ("select", "#username", "A")
        assert engine.call("check", {"ref": "[1]"}).ok
        assert handle.calls[-1] == ("check", "#username")
        assert engine.call("uncheck", {"ref": "[1]"}).ok
        assert handle.calls[-1] == ("uncheck", "#username")
        assert engine.call("scroll", {"direction": "down"}).ok
        assert handle.calls[-1] == ("scroll", "down")
        assert engine.call("download", {"ref": "[1]"}).ok
        assert engine.call("upload", {"ref": "[1]", "path": "x.txt"}).ok
        assert handle.calls[-1] == ("upload", "#username", "x.txt")

    def test_multiple_page_variables_switch_target(self):
        browser = FakeBrowser()
        browser.pages = {
            "1": FakePageHandle(PageRef("1"), url="http://same"),
            "2": FakePageHandle(PageRef("2"), url="http://same"),
        }
        engine, space, frame = build_engine(
            browser,
            probe=FakeProbe(),
            graph_generator=fake_graph_generator(
                make_graph(url="http://same"), make_snapshot(url="http://same")
            ),
        )
        space.write(frame, "$this/A", SchemaPageRef("1", "http://same"), "页面引用")
        space.write(frame, "$this/B", SchemaPageRef("2", "http://same"), "页面引用")
        assert engine.call("semantic_graph", {"scope": "full", "lod": 2}).ok
        assert space.current_page(frame).page_id == "2"

        assert engine.call("click", {"ref": "[1]"}).ok
        assert browser.pages["2"].calls[-1] == ("click", "#username")
        assert browser.pages["1"].calls == []

        space.write(frame, "$this/A", SchemaPageRef("1", "http://same"), "页面引用")
        assert space.current_page(frame).page_id == "1"
        assert engine.call("click", {"ref": "[1]"}).ok
        assert browser.pages["1"].calls[-1] == ("click", "#username")


class TestOpen:
    """任务 5.1：open 写入页面引用变量。"""

    def test_open_writes_page_ref_variable(self):
        browser = FakeBrowser()
        engine, space, frame = build_engine(browser)
        result = engine.call("open", {"url": "http://example.com/login"})
        assert result.ok
        value = space.read(frame, "this/page")
        assert value is not None
        assert value.page_id == "1"
        assert result.detail["page_ref"].id == "1"
        assert result.detail["var"] == "this/page"

    def test_open_failure_returns_failure(self):
        browser = FakeBrowser()
        browser.fail_open = True
        engine, _, _ = build_engine(browser)
        result = engine.call("open", {"url": "http://x"})
        assert result.ok is False
        assert result.detail["code"] == ErrorCode.NETWORK


class TestSemanticGraph:
    """任务 5.2：semantic_graph 委托 M4、无缓存、刷新 ref 映射。"""

    def test_semantic_graph_success(self):
        browser = FakeBrowser()
        engine, _, _ = _seeded(browser)
        result = engine.call("semantic_graph", {"scope": "full", "lod": 2})
        assert result.ok
        assert result.detail["ref_count"] == 1
        assert "text" in result.detail
        assert engine.ref_map.generation >= 1
        assert "[1]" in engine.ref_map.refs

    def test_semantic_graph_program_stage_failure(self):
        browser = FakeBrowser()

        def bad_gen(page_ref, scope="full", lod=2, probe=None, filler=None, budget_limit=None):
            raise ProgramStageError("DOM 爬取失败")

        engine, _, _ = build_engine(browser, graph_generator=bad_gen)
        assert engine.call("open", {"url": "http://x"}).ok
        result = engine.call("semantic_graph", {"scope": "full", "lod": 2})
        assert result.ok is False
        assert "语义图生成失败" in result.error

    def test_semantic_graph_llm_stage_failure(self):
        browser = FakeBrowser()

        def bad_gen(page_ref, scope="full", lod=2, probe=None, filler=None, budget_limit=None):
            raise LlmStageError("模型不可用")

        engine, _, _ = build_engine(browser, graph_generator=bad_gen)
        assert engine.call("open", {"url": "http://x"}).ok
        result = engine.call("semantic_graph", {"scope": "full", "lod": 2})
        assert result.ok is False
        assert "语义图生成失败" in result.error


class TestHttpFormA:
    """任务 5.3：HTTP 形态 A（clear_requests/get_response）。"""

    def test_clear_then_no_match_returns_failure(self):
        browser = FakeBrowser()
        engine, _, _ = build_engine(browser)
        browser.http_recorder.record_response(
            fake_response("POST", "http://example.com/api/login", 200, '{"ok":true}')
        )
        assert engine.call("clear_requests", {}).ok
        result = engine.call("get_response", {"method": "GET", "url_pattern": "/api"})
        assert result.ok is False
        assert "无匹配请求响应" in result.error

    def test_matching_response_returned(self):
        browser = FakeBrowser()
        engine, _, _ = build_engine(browser)
        browser.http_recorder.record_response(
            fake_response("POST", "http://example.com/api/login", 200, '{"ok":true}')
        )
        result = engine.call("get_response", {"method": "post", "url_pattern": "/api"})
        assert result.ok
        assert result.detail["response"].url == "http://example.com/api/login"
        assert result.detail["response"].status == 200


class TestHttpFormB:
    """任务 5.4：HTTP 形态 B（独立请求，认证显式提供）。"""

    def test_request_sent_with_explicit_params(self, monkeypatch):
        browser = FakeBrowser()
        engine, _, _ = build_engine(browser)
        captured: dict = {}

        def stub(method, url, headers=None, body=None):
            captured.update(method=method, url=url, headers=headers, body=body)
            return OpResult(True, detail={"response": "ok"})

        monkeypatch.setattr(engine_module, "_http_request", stub)
        result = engine.call(
            "http_request",
            {
                "method": "GET",
                "url": "http://api.test/x",
                "headers": {"Authorization": "Bearer token"},
                "body": "",
            },
        )
        assert result.ok
        assert captured == {
            "method": "GET",
            "url": "http://api.test/x",
            "headers": {"Authorization": "Bearer token"},
            "body": "",
        }


class TestExtract:
    """任务 5.5：extract 写入变量并类型校验。"""

    def test_extract_writes_variable_with_declared_type(self):
        browser = FakeBrowser()
        engine, space, frame = _seeded(browser, value="42")
        frame.outputs = {"订单号": "订单号"}
        result = engine.call("extract", {"ref": "[1]", "target": "$this/订单号"})
        assert result.ok
        assert result.detail["value"] == "42"
        assert space.read(frame, "$this/订单号") == "42"

    def test_extract_type_mismatch_not_written(self):
        browser = FakeBrowser()
        engine, space, frame = _seeded(browser, value="abc")
        frame.outputs = {"数量": "整数"}
        result = engine.call("extract", {"ref": "[1]", "target": "$this/数量"})
        assert result.ok is False
        assert "类型" in result.error
        assert space.read(frame, "$this/数量") is None


class TestWaitScroll:
    """任务 5.6：wait/scroll 的 Playwright 封装（作用于当前页面）。"""

    def test_wait_uses_default_timeout(self):
        browser = FakeBrowser()
        engine, _, _ = build_engine(browser)
        assert engine.call("open", {"url": "http://x"}).ok
        result = engine.call("wait", {"condition": "selector: #foo"})
        assert result.ok
        assert browser.pages["1"].calls[-1] == ("wait", "selector: #foo", 30000)

    def test_scroll_binds_current_page(self):
        browser = FakeBrowser()
        engine, _, _ = build_engine(browser)
        assert engine.call("open", {"url": "http://x"}).ok
        result = engine.call("scroll", {"direction": "bottom"})
        assert result.ok
        assert browser.pages["1"].calls[-1] == ("scroll", "bottom")


class TestErrorSemantics:
    """任务 6.1/6.2：普通失败回传 vs 致命错误抛出。"""

    def test_non_fatal_failure_returned_as_op_result(self):
        browser = FakeBrowser()
        engine, _, _ = _seeded(browser)
        browser.pages["1"].fail_result = OpResult(
            False, "点击失败", {"code": ErrorCode.NOT_FOUND}
        )
        result = engine.call("click", {"ref": "[1]"})
        assert result.ok is False
        assert result.error == "点击失败"
        assert result.detail["code"] == ErrorCode.NOT_FOUND

    def test_invalid_ref_returns_failure_without_operation(self):
        browser = FakeBrowser()
        engine, _, _ = _seeded(browser)
        result = engine.call("click", {"ref": "[999]"})
        assert result.ok is False
        assert "无效 ref" in result.error
        assert browser.pages["1"].calls == []

    def test_fatal_error_propagates(self):
        browser = FakeBrowser()
        engine, _, _ = _seeded(browser)
        browser.pages["1"].fail_with = FatalBrowserError("浏览器崩溃")
        with pytest.raises(FatalBrowserError):
            engine.call("click", {"ref": "[1]"})

    def test_unexpected_exception_wrapped_as_failure(self):
        browser = FakeBrowser()
        engine, _, _ = _seeded(browser)
        browser.pages["1"].fail_with = RuntimeError("意外异常")
        result = engine.call("click", {"ref": "[1]"})
        assert result.ok is False
        assert "执行失败" in result.error

class TestActivatePage:
    """/5.10 补全：open save_to 命名页签 + activate 切换 + get_url 存文本。"""

    def test_open_with_save_to_stores_named_tab(self):
        browser = FakeBrowser()
        engine, space, frame = build_engine(browser)
        result = engine.call("open", {"url": "http://example.com/login", "save_to": "this/登录页"})
        assert result.ok, result.error
        value = space.read(frame, "this/登录页")
        assert value is not None
        assert isinstance(value, SchemaPageRef)
        assert value.page_id == "1"
        # 默认活动页仍指向该页（open 后成为活动页）
        assert space.current_page(frame).page_id == "1"

    def test_activate_switches_to_named_tab(self):
        browser = FakeBrowser()
        engine, space, frame = build_engine(browser)
        assert engine.call("open", {"url": "http://a", "save_to": "this/页面A"}).ok
        assert engine.call("open", {"url": "http://b", "save_to": "this/页面B"}).ok
        # 当前活动页是 B（最近 open）
        assert space.current_page(frame).url == "http://b"
        # 切回 A
        result = engine.call("activate", {"page_var": "this/页面A"})
        assert result.ok, result.error
        assert space.current_page(frame).page_id == "1"

    def test_activate_non_page_var_fails(self):
        browser = FakeBrowser()
        engine, space, frame = build_engine(browser)
        # 写入一个文本变量（非页签）
        engine.call("get_url", {"save_to": "this/url文本"})
        result = engine.call("activate", {"page_var": "this/url文本"})
        assert result.ok is False
        assert "不是页面引用" in result.error

    def test_activate_undefined_var_fails(self):
        browser = FakeBrowser()
        engine, _, _ = build_engine(browser)
        result = engine.call("activate", {"page_var": "this/不存在"})
        assert result.ok is False

    def test_get_url_stores_string(self):
        browser = FakeBrowser()
        engine, space, frame = build_engine(browser)
        assert engine.call("open", {"url": "http://example.com/login"}).ok
        result = engine.call("get_url", {"save_to": "this/url文本"})
        assert result.ok, result.error
        value = space.read(frame, "this/url文本")
        assert value == "http://example.com/login"
        # 类型为文本（非页面引用）
        assert frame.declared.get("url文本") == "文本"
