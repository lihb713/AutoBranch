"""任务 2.x/4.1/5.1：Action 叶子 agent 式执行（驱动循环/工具回填/结果解析/追踪）。"""

from __future__ import annotations

from fake_transport import chat_response
from leaf_agent_helpers import graph_result, make_ctx, tool_call

from webops.browser import OpResult
from webops.leaf_agent import execute_leaf
from webops.parser.models import ActionNode


def test_action_agent_loop_drives_tool_calls_and_succeeds(config, fake, stub_engine):
    """2.1/2.2/2.3/2.4/4.1：语义图→type→成功，决策序列与追踪数据齐全。"""
    fake.responses = [
        chat_response(tool_calls=[tool_call("semantic_graph", {"scope": "full", "lod": 2})]),
        chat_response(tool_calls=[tool_call("type", {"ref": "[1]", "text": "admin"})]),
        chat_response(text="输入完成\n结果: 成功"),
    ]
    stub_engine.results["semantic_graph"] = graph_result(
        "PAGE: 测试  URL=x\nFIELD [1] 用户名输入框"
    )
    stub_engine.results["type"] = OpResult(True, detail={"var": "$this/用户名"})

    result = execute_leaf(
        ActionNode(description="在用户名输入框输入 admin"),
        make_ctx(config, fake, stub_engine),
    )

    assert result.status == "success"
    assert result.bool_value is None
    assert result.error_source is None
    # 初始语义图获取（M6 自取）+ LLM 调用 semantic_graph + type
    assert [call[0] for call in stub_engine.calls] == [
        "semantic_graph",
        "semantic_graph",
        "type",
    ]
    assert [c.name for c in result.trace.calls] == ["semantic_graph", "type"]
    assert result.trace.calls[1].success is True
    assert result.trace.decision == "输入完成\n结果: 成功"
    assert result.trace.terminator is None
    assert result.trace.llm_reasoning
    assert result.trace.llm_input["description"] == "在用户名输入框输入 admin"
    assert result.trace.llm_input["prompt_version"] == "1.3"


def test_action_function_failure_passed_back_and_corrected(config, fake, stub_engine):
    """5.1 函数失败回传 LLM，LLM 修正后继续（agent 语义，引擎不判断重试）。"""
    fake.responses = [
        chat_response(tool_calls=[tool_call("click", {"ref": "[2]"})]),
        chat_response(tool_calls=[tool_call("type", {"ref": "[2]", "text": "admin"})]),
        chat_response(text="修正后完成\n结果: 成功"),
    ]
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")
    stub_engine.results["click"] = OpResult(False, "元素不可点击", {"code": "NOT_INTERACTABLE"})
    stub_engine.results["type"] = OpResult(True, detail={})

    result = execute_leaf(
        ActionNode(description="在用户名输入框输入 admin"),
        make_ctx(config, fake, stub_engine),
    )

    assert result.status == "success"
    assert [c.name for c in result.trace.calls] == ["click", "type"]
    assert result.trace.calls[0].success is False
    assert "NOT_INTERACTABLE" in result.trace.calls[0].result
    assert result.trace.calls[1].success is True


def test_action_llm_reports_failure(config, fake, stub_engine):
    """4.1 Action 返回失败 → 记为 LLM 侧失败。"""
    fake.responses = [chat_response(text="找不到目标元素\n结果: 失败")]
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(
        ActionNode(description="点击登录"),
        make_ctx(config, fake, stub_engine),
    )

    assert result.status == "failure"
    assert result.error_source == "llm"
    assert result.bool_value is None


def test_action_unparseable_answer_is_llm_failure(config, fake, stub_engine):
    """2.3 无法解析的最终回答 → LLM 侧失败，原始回答保留在 decision。"""
    fake.responses = [chat_response(text="抱歉，我无法完成这个任务")]
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(
        ActionNode(description="点击登录"),
        make_ctx(config, fake, stub_engine),
    )

    assert result.status == "failure"
    assert result.error_source == "llm"
    assert result.trace.decision == "抱歉，我无法完成这个任务"


def test_action_node_type_dispatch(config, fake, stub_engine):
    """1.3 Action 节点分派到 Action 执行路径（系统提示词为执行代理模板）。"""
    fake.responses = [chat_response(text="结果: 成功")]
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(ActionNode(description="点击登录"), make_ctx(config, fake, stub_engine))

    assert result.status == "success"
    assert result.trace.llm_input["node_type"] == "action"
