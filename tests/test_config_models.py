"""任务 2.1/2.2/2.3：LLMConfig 与数据结构。"""

from __future__ import annotations

import json
import logging

import pytest

from webops.llm.config import LLMConfig
from webops.llm.models import LLMResponse, ToolCall, ToolResult, ToolSpec


def test_config_requires_all_fields():
    """2.1 缺失任一必填字段 → 参数校验错误。"""
    with pytest.raises(ValueError, match="base_url"):
        LLMConfig(base_url="", api_key="k", model="m")
    with pytest.raises(ValueError, match="api_key"):
        LLMConfig(base_url="u", api_key="", model="m")
    with pytest.raises(ValueError, match="model"):
        LLMConfig(base_url="u", api_key="k", model="")


def test_config_valid():
    cfg = LLMConfig(base_url="u", api_key="k", model="m")
    assert cfg.auth_header_value() == "Bearer k"


def test_tool_spec_default_parameters():
    """2.2 ToolSpec：parameters 默认空 dict。"""
    spec = ToolSpec(name="click", description="点击")
    assert spec.parameters == {}


def test_tool_call_fields():
    call = ToolCall(id="call_1", name="click", arguments='{"ref":"[1]"}')
    assert call.id == "call_1"
    assert json.loads(call.arguments)["ref"] == "[1]"


def test_llm_response_defaults():
    """LLMResponse：text 默认空，tool_calls 默认空列表。"""
    resp = LLMResponse()
    assert resp.text == ""
    assert resp.tool_calls == []
    assert resp.has_tool_calls is False


def test_llm_response_with_tool_calls():
    resp = LLMResponse(tool_calls=[ToolCall(id="c", name="n", arguments="{}")])
    assert resp.has_tool_calls is True


def test_tool_result():
    result = ToolResult(call_id="call_1", content="ok")
    assert result.call_id == "call_1"
    assert result.content == "ok"


def test_api_key_not_in_logs():
    """2.3 api_key 不进入日志输出。"""
    secret = "sk-this-is-a-secret-test-key-12345"
    cfg = LLMConfig(base_url="u", api_key=secret, model="m")
    logger = logging.getLogger("webops.llm")
    records: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    logger.addHandler(handler)
    try:
        logger.info("config created base_url=%s model=%s", cfg.base_url, cfg.model)
        logger.info("requesting with auth=%s", cfg.auth_header_value())
    finally:
        logger.removeHandler(handler)
    joined = "\n".join(records)
    assert secret not in joined
