"""任务 4.2：Condition 叶子 agent 式判断（确定布尔值，推理期间引擎不介入）。"""

from __future__ import annotations

from fake_transport import chat_response
from leaf_agent_helpers import graph_result, make_ctx, tool_call

from webops.leaf_agent import execute_leaf
from webops.parser.models import ConditionNode


def test_condition_true(config, fake, stub_engine):
    """4.2 条件满足 → 返回确定布尔值真。"""
    fake.responses = [
        chat_response(tool_calls=[tool_call("semantic_graph", {"scope": "full", "lod": 2})]),
        chat_response(text="页面已出现订单号\n结果: 真"),
    ]
    stub_engine.results["semantic_graph"] = graph_result(
        "PAGE: 测试  URL=x\nTEXT [2] 订单号：12345"
    )

    result = execute_leaf(
        ConditionNode(description="页面上出现'订单号：12345'"),
        make_ctx(config, fake, stub_engine),
    )

    assert result.status == "success"
    assert result.bool_value is True
    assert result.error_source is None


def test_condition_false_is_normal_result(config, fake, stub_engine):
    """4.2 条件不满足 → 返回确定布尔值假（正常节点结果，非错误）。"""
    fake.responses = [
        chat_response(tool_calls=[tool_call("semantic_graph", {"scope": "full", "lod": 2})]),
        chat_response(text="结果: 假"),
    ]
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(
        ConditionNode(description="登录按钮是灰的"),
        make_ctx(config, fake, stub_engine),
    )

    assert result.status == "failure"
    assert result.bool_value is False
    assert result.error_source is None


def test_condition_indeterminate_is_llm_failure(config, fake, stub_engine):
    """4.2 无法得出确定判断 → LLM 侧失败（定位终止场景）。"""
    fake.responses = [chat_response(text="无法判断\n结果: 失败")]
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(
        ConditionNode(description="登录按钮是灰的"),
        make_ctx(config, fake, stub_engine),
    )

    assert result.status == "failure"
    assert result.bool_value is None
    assert result.error_source == "llm"


def test_condition_reasoning_does_not_call_operation_tools(config, fake, stub_engine):
    """4.2 推理期间引擎不介入：只调用 semantic_graph，不调用操作类函数。"""
    fake.responses = [
        chat_response(tool_calls=[tool_call("semantic_graph", {"scope": "full", "lod": 2})]),
        chat_response(text="结果: 真"),
    ]
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    execute_leaf(
        ConditionNode(description="跳转到了个人中心"),
        make_ctx(config, fake, stub_engine),
    )

    assert set(call[0] for call in stub_engine.calls) == {"semantic_graph"}


def test_condition_node_type_dispatch(config, fake, stub_engine):
    """1.3 Condition 节点分派到 Condition 执行路径（判断代理模板）。"""
    fake.responses = [chat_response(text="结果: 假")]
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(
        ConditionNode(description="按钮是灰的"),
        make_ctx(config, fake, stub_engine),
    )

    assert result.status == "failure"
    assert result.trace.llm_input["node_type"] == "condition"
    assert result.bool_value is False
