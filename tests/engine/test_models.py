"""M5 任务 1.x：包结构、OpResult 与 FatalBrowserError、ToolSpec 序列化。"""

from __future__ import annotations

import json

import pytest

from webops.engine import (
    ENGINE_TOOLS,
    FatalBrowserError,
    OpResult,
    ToolSpec,
    failure,
    success,
)


class TestPackage:
    """任务 1.1：M5 模块包可导入，pytest 收集到该模块测试。"""

    def test_package_importable(self):
        import webops.engine as engine

        assert hasattr(engine, "ENGINE_TOOLS")
        assert hasattr(engine, "EngineFunctions")
        assert hasattr(engine, "EngineRefMap")
        assert hasattr(engine, "OpResult")
        assert hasattr(engine, "FatalBrowserError")


class TestOpResult:
    """任务 1.2：OpResult 成功/失败两种构造与 FatalBrowserError。"""

    def test_success_construction(self):
        result = OpResult(True)
        assert result.ok is True
        assert result.error is None

        result_with_detail = success({"page_ref": "P1"})
        assert result_with_detail.ok is True
        assert result_with_detail.detail == {"page_ref": "P1"}

    def test_failure_construction(self):
        result = OpResult(False, "点击失败", {"code": "INVALID_REF"})
        assert result.ok is False
        assert result.error == "点击失败"
        assert result.detail["code"] == "INVALID_REF"

        result_via_helper = failure("出错了", code="NETWORK")
        assert result_via_helper.ok is False
        assert result_via_helper.error == "出错了"
        assert result_via_helper.detail["code"] == "NETWORK"

    def test_fatal_browser_error_is_exception(self):
        exc = FatalBrowserError("浏览器崩溃")
        assert isinstance(exc, Exception)
        with pytest.raises(FatalBrowserError):
            raise exc


class TestToolSpec:
    """任务 1.3：ToolSpec 序列化为 LLM 可解析的工具定义 JSON。"""

    def test_tool_spec_has_contract_fields(self):
        spec = ENGINE_TOOLS[0]
        assert spec.name == "open"
        assert isinstance(spec.description, str) and spec.description
        assert spec.parameters["type"] == "object"
        assert "properties" in spec.parameters
        assert "required" in spec.parameters

    def test_tool_spec_serializes_to_json(self):
        spec = ENGINE_TOOLS[0]
        payload = json.dumps(
            {"name": spec.name, "description": spec.description, "parameters": spec.parameters},
            ensure_ascii=False,
        )
        parsed = json.loads(payload)
        assert parsed["name"] == spec.name
        assert parsed["parameters"]["type"] == "object"

    def test_all_tools_are_json_serializable(self):
        for spec in ENGINE_TOOLS:
            payload = json.dumps(
                {"name": spec.name, "parameters": spec.parameters},
                ensure_ascii=False,
            )
            assert json.loads(payload)["name"] == spec.name
            assert isinstance(spec, ToolSpec)
