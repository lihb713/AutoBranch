"""任务 6.3/6.4：提示词/决策回归保护与 mock M5 串联冒烟测试。"""

from __future__ import annotations

from fake_transport import chat_response
from leaf_agent_helpers import graph_result, make_ctx, tool_call

from autobranch.browser import OpResult
from autobranch.leaf_agent import build_system_prompt, build_user_message, execute_leaf
from autobranch.parser.models import ActionNode, ConditionNode


def test_decision_sequence_regression(config, fake, stub_engine):
    """6.3 固定输入 + 固定 mock 桩 → LLM 决策序列与结果可回归（防决策漂移）。"""
    fake.responses = [
        chat_response(
            tool_calls=[tool_call("browser.semantic_graph", {"scope": "full", "lod": 2})]
        ),
        chat_response(tool_calls=[tool_call("browser.type", {"ref": "[1]", "text": "admin"})]),
        chat_response(text="完成\n结果: 成功"),
    ]
    stub_engine.results["browser.semantic_graph"] = graph_result(
        "PAGE: 测试  URL=x\nFIELD [1] 用户名输入框"
    )
    stub_engine.results["browser.type"] = OpResult(True, detail={})

    result = execute_leaf(
        ActionNode(description="在用户名输入框输入 admin"),
        make_ctx(config, fake, stub_engine),
    )

    assert result.status == "success"
    assert [c.name for c in result.trace.calls] == ["browser.semantic_graph", "browser.type"]
    assert result.trace.calls[1].arguments == {"ref": "[1]", "text": "admin"}
    assert result.trace.llm_input["prompt_version"] == "1.6"


def test_prompt_rendering_regression_golden():
    """6.3 固定输入 → 提示词渲染结果固定（金样本断言，变更提示词需同步更新）。"""
    node = ActionNode(description="在用户名输入框输入 admin")
    system = build_system_prompt(node, schema_hint="可用引擎函数: semantic_graph, click, type")
    user = build_user_message(
        "在用户名输入框输入 admin",
        "PAGE: 登录页  URL=https://example.com/login\nFIELD [1] 用户名输入框",
    )
    assert "你是一个 Web 自动化执行代理" in system
    assert "可用引擎函数: semantic_graph, click, type" in system
    assert "结果: 成功" in system
    assert user == (
        "节点描述: 在用户名输入框输入 admin\n\n当前页面语义图:\n"
        "PAGE: 登录页  URL=https://example.com/login\nFIELD [1] 用户名输入框"
    )


def test_smoke_action_and_condition_full_trace(config, fake, stub_engine):
    """6.4 mock M5 下串联冒烟：Action + Condition 完整执行，结果与追踪字段齐全。"""
    stub_engine.results["browser.semantic_graph"] = graph_result(
        "PAGE: 测试  URL=x\nFIELD [1] 用户名输入框\nTEXT [2] 订单号：12345"
    )
    stub_engine.results["browser.type"] = OpResult(True, detail={})

    # Action 叶子完整执行
    fake.responses = [
        chat_response(tool_calls=[tool_call("browser.type", {"ref": "[1]", "text": "admin"})]),
        chat_response(text="结果: 成功"),
    ]
    action_result = execute_leaf(
        ActionNode(description="在用户名输入框输入 admin"),
        make_ctx(config, fake, stub_engine),
    )

    assert action_result.status == "success"
    assert action_result.bool_value is None
    assert action_result.error_source is None
    assert action_result.trace.llm_input
    assert action_result.trace.llm_reasoning
    assert action_result.trace.decision
    assert action_result.trace.calls and action_result.trace.calls[0].name == "browser.type"
    assert action_result.trace.terminator is None

    # Condition 叶子完整执行（连续驱动，独立会话）
    fake.responses = [
        chat_response(
            tool_calls=[tool_call("browser.semantic_graph", {"scope": "full", "lod": 2})]
        ),
        chat_response(text="结果: 真"),
    ]
    condition_result = execute_leaf(
        ConditionNode(description="页面上出现'订单号：12345'"),
        make_ctx(config, fake, stub_engine),
    )

    assert condition_result.status == "success"
    assert condition_result.bool_value is True
    assert condition_result.trace.llm_input["node_type"] == "condition"
    assert condition_result.trace.calls
    assert condition_result.trace.terminator is None
