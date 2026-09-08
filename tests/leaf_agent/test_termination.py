"""任务 3.x：引擎兜底终止条件（轮数上限/连续无进展/超时）与定位终止子集覆盖。"""

from __future__ import annotations

from fake_transport import chat_response
from leaf_agent_helpers import SlowTransport, graph_result, make_ctx, tool_call

from webops.leaf_agent import execute_leaf
from webops.parser.models import ActionNode, ConditionNode


def test_round_limit_terminates_leaf(config, fake, stub_engine):
    """3.1 超过对话轮数上限 → 终止叶子并记录 terminator，标记 LLM 侧失败。"""
    # 每轮 lod 递增使指纹不同，避免先触发无进展
    fake.responses = [
        chat_response(
            tool_calls=[tool_call("semantic_graph", {"scope": "full", "lod": i})]
        )
        for i in range(11)
    ]
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(
        ActionNode(description="点击登录"),
        make_ctx(config, fake, stub_engine, max_rounds=10),
    )

    assert result.status == "failure"
    assert result.error_source == "llm"
    assert result.trace.terminator == "round_limit"
    assert len(result.trace.calls) == 10


def test_no_progress_terminates_leaf(config, fake, stub_engine):
    """3.2 连续 2 轮相同调用/结果（无进展）→ 终止并记录触发条件。"""
    call = tool_call("semantic_graph", {"scope": "full", "lod": 2})
    fake.responses = [chat_response(tool_calls=[call]), chat_response(tool_calls=[call])]
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(
        ActionNode(description="点击登录"),
        make_ctx(config, fake, stub_engine, no_progress_rounds=2),
    )

    assert result.status == "failure"
    assert result.error_source == "llm"
    assert result.trace.terminator == "no_progress"
    assert len(result.trace.calls) == 2


def test_leaf_timeout_terminates(config, fake, stub_engine):
    """3.3 单叶子墙钟超时 → 终止并记录触发条件。"""
    call = tool_call("semantic_graph", {"scope": "full", "lod": 2})
    slow = SlowTransport(delay=0.05, responses=[chat_response(tool_calls=[call])])
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x")

    result = execute_leaf(
        ActionNode(description="点击登录"),
        make_ctx(config, slow, stub_engine, timeout=0.01),
    )

    assert result.status == "failure"
    assert result.error_source == "llm"
    assert result.trace.terminator == "timeout"


def test_location_termination_is_covered_by_leaf_termination(config, fake, stub_engine):
    """3.4 定位终止（§9.7）作为叶子终止子集：连续相同语义图调用 → LLM 侧失败。"""
    call = tool_call("semantic_graph", {"scope": "F1", "lod": 3})
    fake.responses = [chat_response(tool_calls=[call]), chat_response(tool_calls=[call])]
    stub_engine.results["semantic_graph"] = graph_result("PAGE: 测试  URL=x\nFIELD [3] 目标")

    result = execute_leaf(
        ConditionNode(description="定位目标元素"),
        make_ctx(config, fake, stub_engine, no_progress_rounds=2),
    )

    assert result.status == "failure"
    assert result.error_source == "llm"
    assert result.trace.terminator == "no_progress"
