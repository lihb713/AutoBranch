"""任务 8.1：集成测试——配置 → 多轮工具调用 → 预算检测 → 错误分类全链路。

全部基于 FakeTransport，不依赖真实 API/浏览器。
"""

from __future__ import annotations

import pytest
from fake_transport import chat_response

from autobranch.llm.config import LLMConfig
from autobranch.llm.errors import LLMAuthError, LLMBudgetExceeded
from autobranch.llm.models import ToolResult, ToolSpec
from autobranch.llm.session import LLMSession


@pytest.mark.integration
def test_full_pipeline_multi_tool_with_budget(config, fake):
    """全链路：配置 → 多轮工具调用 → token 累积 → 预算未超正常完成。"""
    fake.responses = [
        chat_response(
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "lookup_order", "arguments": '{"order_id":"ORD-001"}'},
                }
            ],
            usage={"total_tokens": 20},
        ),
        chat_response(
            tool_calls=[
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "approve_order", "arguments": '{"order_id":"ORD-001"}'},
                }
            ],
            usage={"total_tokens": 20},
        ),
        chat_response(text="订单已批准", usage={"total_tokens": 10}),
    ]
    tools = [
        ToolSpec(name="lookup_order", description="查订单"),
        ToolSpec(name="approve_order", description="批准订单"),
    ]
    session = LLMSession(
        config=config, system_prompt="你是订单助手", transport=fake, budget_limit=200
    )
    session.add_user_message("批准订单 ORD-001")

    # 多轮工具循环
    for _ in range(2):
        resp = session.request(tools=tools)
        assert resp.has_tool_calls
        call = resp.tool_calls[0]
        session.add_tool_result(call.id, ToolResult(call_id=call.id, content="done"))

    final = session.request(tools=tools)
    assert final.text == "订单已批准"
    assert session.token_used() == 50
    assert not session.exceeds_budget(200)


@pytest.mark.integration
def test_full_pipeline_budget_exceeded_terminates(config, fake):
    """预算超限时终止叶子（多轮累积触发）。"""
    fake.responses = [
        chat_response(
            tool_calls=[
                {
                    "id": "call_a",
                    "type": "function",
                    "function": {"name": "run", "arguments": "{}"},
                }
            ],
            usage={"total_tokens": 80},
        ),
        chat_response(
            tool_calls=[
                {
                    "id": "call_b",
                    "type": "function",
                    "function": {"name": "run", "arguments": "{}"},
                }
            ],
            usage={"total_tokens": 80},
        ),
    ]
    session = LLMSession(config=config, system_prompt="s", transport=fake, budget_limit=100)
    session.add_user_message("跑")
    first = session.request(tools=[ToolSpec(name="run", description="执行")])
    session.add_tool_result(first.tool_calls[0].id, "ok")
    with pytest.raises(LLMBudgetExceeded):
        session.request(tools=[ToolSpec(name="run", description="执行")])


@pytest.mark.integration
def test_full_pipeline_error_dispatch(config, fake):
    """错误分类：鉴权失败被识别为配置问题。"""
    fake.responses = [(401, '{"error":"bad key"}')]
    session = LLMSession(config=config, system_prompt="s", transport=fake)
    session.add_user_message("hi")
    with pytest.raises(LLMAuthError):
        session.request()


@pytest.mark.integration
def test_config_validation_and_auth_header():
    """配置必填校验 + 鉴权头正确（不依赖网络）。"""
    with pytest.raises(ValueError):
        LLMConfig(base_url="", api_key="k", model="m")
    cfg = LLMConfig(base_url="https://api.deepseek.com", api_key="sk-test", model="m")
    assert cfg.auth_header_value() == "Bearer sk-test"
