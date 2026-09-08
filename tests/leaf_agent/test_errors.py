"""任务 5.2/5.3：错误边界与错误来源分类（LLM 侧 vs 程序侧）。"""

from __future__ import annotations

from fake_transport import chat_response
from leaf_agent_helpers import graph_result, make_ctx, tool_call

from webops.browser import FatalBrowserError
from webops.leaf_agent import execute_leaf
from webops.llm import LLMBudgetExceeded, LLMConnectionError, LLMTimeoutError
from webops.parser.models import ActionNode, ConditionNode


def test_fatal_browser_error_during_loop_is_program_failure(config, fake, stub_engine):
    """5.2 致命错误（浏览器崩溃）发生在工具调用中 → 终止整个流程并分类为程序侧失败。"""
    fake.responses = [chat_response(tool_calls=[tool_call("click", {"ref": "[1]"})])]
    stub_engine.raise_on["click"] = FatalBrowserError("浏览器崩溃")
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(ActionNode(description="点击登录"), make_ctx(config, fake, stub_engine))

    assert result.status == "failure"
    assert result.error_source == "program"
    assert result.trace.terminator == "fatal_error"


def test_llm_connection_error_is_program_failure(config, fake, stub_engine):
    """5.2/5.3 LLM 连接失败 → 程序侧失败（可重试语义）。"""
    fake.error = LLMConnectionError("连接失败")
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(ActionNode(description="点击登录"), make_ctx(config, fake, stub_engine))

    assert result.status == "failure"
    assert result.error_source == "program"
    assert result.trace.terminator == "llm_connection"


def test_llm_timeout_is_program_failure(config, fake, stub_engine):
    """5.2/5.3 LLM 请求超时 → 程序侧失败。"""
    fake.error = LLMTimeoutError("请求超时")
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(ActionNode(description="点击登录"), make_ctx(config, fake, stub_engine))

    assert result.status == "failure"
    assert result.error_source == "program"
    assert result.trace.terminator == "llm_timeout"


def test_llm_budget_exceeded_is_llm_failure(config, fake, stub_engine):
    """5.3 token 预算超限（§9.7 定位终止子集）→ LLM 侧失败。"""
    fake.error = LLMBudgetExceeded("token 预算超限")
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(ActionNode(description="点击登录"), make_ctx(config, fake, stub_engine))

    assert result.status == "failure"
    assert result.error_source == "llm"
    assert result.trace.terminator == "budget"


def test_termination_classified_as_llm(config, fake, stub_engine):
    """5.3 终止条件触发的失败一律归 LLM 侧。"""
    call = tool_call("semantic_graph", {"scope": "full", "lod": 2})
    fake.responses = [chat_response(tool_calls=[call]), chat_response(tool_calls=[call])]
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(
        ActionNode(description="点击登录"),
        make_ctx(config, fake, stub_engine, max_rounds=1),
    )

    assert result.status == "failure"
    assert result.error_source == "llm"
    assert result.trace.terminator == "round_limit"


def test_condition_determinate_false_is_not_error(config, fake, stub_engine):
    """5.3 Condition 确定判断（假）是正常节点结果，error_source 为 None。"""
    fake.responses = [chat_response(text="结果: 假")]
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(
        ConditionNode(description="登录按钮是灰的"),
        make_ctx(config, fake, stub_engine),
    )

    assert result.status == "failure"
    assert result.bool_value is False
    assert result.error_source is None
