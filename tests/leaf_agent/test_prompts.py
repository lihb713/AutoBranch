"""任务 4.3：提示词模板装配（固定输入 → 稳定渲染）与最终回答解析。"""

from __future__ import annotations

import pytest

from autobranch.leaf_agent.prompts import (
    PROMPT_VERSION,
    DecisionError,
    build_system_prompt,
    build_user_message,
    parse_final_decision,
)
from autobranch.parser.models import ActionNode, ConditionNode


def test_prompt_render_is_deterministic():
    """4.3 固定输入下两次渲染结果一致（可回归）。"""
    node = ActionNode(description="在用户名输入框输入 admin", css_hint="input#username")
    hint = "可用引擎函数: semantic_graph, click, type"
    expected = build_system_prompt(node, schema_hint=hint)
    assert build_system_prompt(node, schema_hint=hint) == expected
    user = build_user_message(node.description, "PAGE: 测试  URL=x", node.css_hint)
    assert user == build_user_message(node.description, "PAGE: 测试  URL=x", node.css_hint)


def test_prompt_version_is_stable():
    """4.3 提示词带版本号。"""
    assert PROMPT_VERSION == "1.4"


def test_system_prompt_differentiates_node_type():
    """4.3 Action/Condition 使用不同角色模板。"""
    action = ActionNode(description="点击登录")
    condition = ConditionNode(description="页面上出现订单号")
    action_prompt = build_system_prompt(action, schema_hint="hint")
    condition_prompt = build_system_prompt(condition, schema_hint="hint")
    assert "执行代理" in action_prompt
    assert "判断代理" in condition_prompt
    assert "结果: 成功" in action_prompt
    assert "结果: 真" in condition_prompt


def test_user_message_includes_description_and_graph():
    """4.3 用户消息 = 节点描述 + 语义图正文（含可选 CSS 提示）。"""
    msg = build_user_message(
        "输入用户名",
        "PAGE: 测试  URL=x\nFIELD [1] 用户名输入框",
        css_hint="#u",
    )
    assert "输入用户名" in msg
    assert "FIELD [1] 用户名输入框" in msg
    assert "CSS 提示: #u" in msg


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("完成\n结果: 成功", ("success", None)),
        ("结果: 失败", ("failure", None)),
        ('{"status": "success"}', ("success", None)),
    ],
)
def test_parse_action_decision(text, expected):
    """2.3 Action 最终回答解析。"""
    assert parse_final_decision(text, "action") == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("页面已出现\n结果: 真", ("success", True)),
        ("结果: 假", ("failure", False)),
        ('{"bool_value": true}', ("success", True)),
    ],
)
def test_parse_condition_decision(text, expected):
    """2.3 Condition 最终回答解析为确定布尔值。"""
    assert parse_final_decision(text, "condition") == expected


def test_parse_condition_indeterminate_raises():
    """2.3 Condition 的 `结果: 失败` 表示无法确定 → DecisionError。"""
    with pytest.raises(DecisionError):
        parse_final_decision("结果: 失败", "condition")


def test_parse_unrecognizable_raises():
    """2.3 无法识别的回答 → DecisionError。"""
    with pytest.raises(DecisionError):
        parse_final_decision("抱歉我做不到", "action")
