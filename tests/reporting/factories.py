"""M8 报告机制测试数据工厂（mock M1/M6/M7 数据，不启动真实浏览器/LLM）。"""

from __future__ import annotations

from webops.reporting.models import (
    ActionCall,
    LeafTrace,
    NodeReport,
    ToolCallRecord,
)

TIMESTAMP = "2026-08-29T10:00:00"
URL = "https://example.com/login"


def make_trace(decision: str | None = "调用 click 点击 #login") -> LeafTrace:
    return LeafTrace(
        llm_input={"node_desc": "点击登录", "semantic_graph": "graph-1"},
        llm_reasoning=["选择函数 click", "判断依据: 按钮可见"],
        decision=decision,
        calls=[ToolCallRecord("click", {"ref": "#login"}, result="成功", success=True)],
    )


def make_report(
    node_type: str = "Action",
    node_desc: str = "点击登录",
    result: str = "success",
    action_call: ActionCall | None = None,
    condition_result: bool | None = None,
    page_url: str | None = URL,
    screenshot_path: str | None = None,
    llm_trace: LeafTrace | None = None,
    timestamp: str = TIMESTAMP,
) -> NodeReport:
    return NodeReport(
        node_type=node_type,
        node_desc=node_desc,
        result=result,
        timestamp=timestamp,
        action_call=action_call,
        condition_result=condition_result,
        page_url=page_url,
        screenshot_path=screenshot_path,
        llm_trace=llm_trace,
    )


def make_action_report(**overrides) -> NodeReport:
    defaults = dict(
        node_type="Action",
        node_desc="点击登录",
        result="success",
        action_call=ActionCall("click", True, arguments={"ref": "#login"}),
        llm_trace=make_trace(),
    )
    defaults.update(overrides)
    return make_report(**defaults)


def make_condition_report(**overrides) -> NodeReport:
    defaults = dict(
        node_type="Condition",
        node_desc="工作台可见",
        result="success",
        condition_result=True,
    )
    defaults.update(overrides)
    return make_report(**defaults)


def make_composite_report(**overrides) -> NodeReport:
    defaults = dict(
        node_type="Sequence",
        node_desc="登录流程",
        result="success",
    )
    defaults.update(overrides)
    return make_report(**defaults)
