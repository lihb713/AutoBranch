"""M5 任务 2.x：ENGINE_TOOLS 注册表、分发与可扩展性。"""

from __future__ import annotations

from engine_helpers import (
    FakeBrowser,
    FakeProbe,
    build_engine,
    fake_graph_generator,
    make_graph,
    make_snapshot,
)

from webops.engine import ENGINE_TOOLS, EngineFunctions, OpResult, ToolSpec
from webops.engine import engine as engine_module

CONTRACT_SIGNATURES: dict[str, list[str]] = {
    "open": ["url"],
    "activate": ["page_var"],
    "get_url": ["save_to"],
    "click": ["ref"],
    "type": ["ref", "text"],
    "select": ["ref", "option"],
    "check": ["ref"],
    "uncheck": ["ref"],
    "scroll": ["direction"],
    "wait": ["condition"],
    "download": ["ref"],
    "upload": ["ref", "path"],
    "semantic_graph": ["scope", "lod"],
    "clear_requests": [],
    "get_response": ["method", "url_pattern"],
    "http_request": ["method", "url"],
    "extract": ["ref", "target"],
}

# 可选参数（在 properties 中但非必需）
_OPTIONAL_PARAMS: dict[str, list[str]] = {
    "http_request": ["headers", "body"],
    "open": ["save_to"],
}


class TestRegistry:
    """任务 2.1：注册表包含 17 个函数，参数与契约签名一致（§5.1/§5.2）。"""

    def test_registry_has_exactly_17_tools(self):
        assert len(ENGINE_TOOLS) == 17

    def test_registry_names_match_contract(self):
        names = [tool.name for tool in ENGINE_TOOLS]
        assert names == list(CONTRACT_SIGNATURES)

    def test_each_tool_parameters_match_signature(self):
        for tool in ENGINE_TOOLS:
            params = tool.parameters
            assert params["type"] == "object"
            props = set(params["properties"])
            optional = set(_OPTIONAL_PARAMS.get(tool.name, []))
            assert props == set(CONTRACT_SIGNATURES[tool.name]) | optional, tool.name
            assert set(params["required"]) == set(CONTRACT_SIGNATURES[tool.name]), tool.name


class TestDispatch:
    """任务 2.2：注册表到执行实现的分发（按函数名调用对应方法）。"""

    def _seeded_engine(self, browser):
        engine, space, frame = build_engine(
            browser,
            probe=FakeProbe(),
            graph_generator=fake_graph_generator(make_graph(), make_snapshot()),
        )
        assert engine.call("open", {"url": "http://example.com/page"}).ok
        assert engine.call("semantic_graph", {"scope": "full", "lod": 2}).ok
        return engine, space, frame

    def test_every_registered_function_dispatches(self, monkeypatch):
        browser = FakeBrowser()
        engine, space, frame = self._seeded_engine(browser)
        calls = []
        monkeypatch.setattr(
            engine_module,
            "_http_request",
            lambda method, url, headers=None, body=None: OpResult(
                True, detail={"method": method, "url": url}
            ),
        )
        args_by_name = {
            "open": {"url": "http://example.com/page"},
            "activate": {"page_var": "this/page"},
            "get_url": {"save_to": "this/当前url"},
            "click": {"ref": "[1]"},
            "type": {"ref": "[1]", "text": "hello"},
            "select": {"ref": "[1]", "option": "A"},
            "check": {"ref": "[1]"},
            "uncheck": {"ref": "[1]"},
            "scroll": {"direction": "down"},
            "wait": {"condition": "selector: #username"},
            "download": {"ref": "[1]"},
            "upload": {"ref": "[1]", "path": "x.txt"},
            "semantic_graph": {"scope": "full", "lod": 2},
            "clear_requests": {},
            "get_response": {"method": "GET", "url_pattern": "/api"},
            "http_request": {"method": "POST", "url": "http://api.test", "headers": {"a": "1"}},
            "extract": {"ref": "[1]", "target": "$this/结果"},
        }
        for name, args in args_by_name.items():
            result = engine.call(name, args)
            assert isinstance(result, OpResult), name
            if name == "get_response":
                # 无匹配记录返回 ok=False（NOT_FOUND）恰好证明该方法被调用
                assert result.detail.get("code") == "NOT_FOUND", name
            else:
                assert result.ok, f"{name}: {result.error}"
            calls.append(name)
        assert calls == list(args_by_name)

    def test_unknown_function_returns_failure(self):
        engine, _, _ = build_engine(FakeBrowser())
        result = engine.call("no_such_function", {})
        assert result.ok is False
        assert "未知引擎函数" in result.error

    def test_missing_argument_returns_failure(self):
        engine, _, _ = build_engine(FakeBrowser())
        result = engine.call("click", {})
        assert result.ok is False
        assert "参数错误" in result.error

    def test_bad_argument_type_returns_failure(self):
        engine, _, _ = build_engine(FakeBrowser())
        result = engine.call("click", "not-a-dict")
        assert result.ok is False
        assert "参数必须是对象" in result.error


class TestExtensibility:
    """任务 2.3：新增函数即注册即用，不改既有代码。"""

    def test_new_function_registered_and_dispatched(self):
        browser = FakeBrowser()
        engine, _, _ = build_engine(browser)
        ENGINE_TOOLS.append(
            ToolSpec(
                name="ping",
                description="测试用复合函数",
                parameters={
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                    "required": ["x"],
                },
            )
        )
        try:

            def ping(self, x: str) -> OpResult:
                return OpResult(True, detail={"echo": x})

            EngineFunctions.ping = ping
            try:
                assert "ping" in [tool.name for tool in ENGINE_TOOLS]
                result = engine.call("ping", {"x": "hello"})
                assert result.ok and result.detail["echo"] == "hello"
                assert isinstance(engine, EngineFunctions)
            finally:
                del EngineFunctions.ping
        finally:
            ENGINE_TOOLS.pop()
        assert "ping" not in [tool.name for tool in ENGINE_TOOLS]
