"""M8 任务 1.1 / 1.3：NodeReport 与 ExecState/NodeInfo 数据契约。"""

from __future__ import annotations

import json
from dataclasses import asdict

from reporting.factories import (
    TIMESTAMP,
    URL,
    make_action_report,
    make_composite_report,
    make_condition_report,
    make_trace,
)

from webops.reporting.models import ActionCall, ExecState, NodeInfo


class TestNodeReport:
    """任务 1.1：NodeReport 各字段可 mock 赋值并可序列化。"""

    def test_action_report_all_fields(self):
        report = make_action_report(
            page_url=URL,
            screenshot_path="/data/reports/run-1/001_click_login.png",
        )
        assert report.node_type == "Action"
        assert report.node_desc == "点击登录"
        assert report.result == "success"
        assert report.timestamp == TIMESTAMP
        assert report.page_url == URL
        assert report.action_call is not None
        assert report.action_call.function == "click"
        assert report.action_call.success is True
        assert report.screenshot_path == "/data/reports/run-1/001_click_login.png"
        assert report.llm_trace is not None

    def test_condition_report_only_condition_field(self):
        report = make_action_report(
            node_type="Condition",
            node_desc="工作台可见",
            condition_result=False,
            action_call=None,
            llm_trace=None,
        )
        assert report.condition_result is False
        assert report.action_call is None
        assert report.screenshot_path is None

    def test_composite_report_special_fields_nullable(self):
        report = make_action_report(
            node_type="Sequence",
            node_desc="登录流程",
            action_call=None,
            llm_trace=None,
        )
        assert report.action_call is None
        assert report.condition_result is None
        assert report.screenshot_path is None
        assert report.llm_trace is None
        assert report.result == "success"

    def test_failure_node_serializable(self):
        report = make_action_report(result="failure")
        assert report.result == "failure"

    def test_action_call_fields(self):
        call = ActionCall(
            "type",
            False,
            arguments={"ref": "#user", "text": "a"},
            error="元素不可见",
        )
        assert call.function == "type"
        assert call.success is False
        assert call.arguments == {"ref": "#user", "text": "a"}
        assert call.error == "元素不可见"

    def test_leaf_trace_fields(self):
        trace = make_trace()
        assert trace.llm_input["node_desc"] == "点击登录"
        assert trace.llm_reasoning == ["选择函数 click", "判断依据: 按钮可见"]
        assert trace.decision == "调用 click 点击 #login"
        assert trace.calls[0].name == "click"
        assert trace.calls[0].success is True

    def test_node_report_serialization_round_trip(self):
        report = make_action_report(
            screenshot_path="/data/reports/run-1/001_click_login.png",
            llm_trace=make_trace(),
        )
        payload = json.dumps(asdict(report), ensure_ascii=False)
        restored = json.loads(payload)
        assert restored["node_type"] == "Action"
        assert restored["node_desc"] == "点击登录"
        assert restored["result"] == "success"
        assert restored["action_call"]["function"] == "click"
        assert restored["action_call"]["success"] is True
        assert restored["condition_result"] is None
        assert restored["screenshot_path"] == "/data/reports/run-1/001_click_login.png"
        assert restored["llm_trace"]["decision"] == "调用 click 点击 #login"
        assert restored["llm_trace"]["calls"][0]["name"] == "click"


class TestNodeInfo:
    """任务 1.3（部分）：NodeInfo 可 mock 构造并查询。"""

    def test_node_info_fields(self):
        info = NodeInfo(node_type="Action", node_desc="点击登录")
        assert info.node_type == "Action"
        assert info.node_desc == "点击登录"


class TestExecState:
    """任务 1.3：ExecState 可 mock 构造并查询，progress 按单数据源派生。"""

    def test_empty_state_progress_zero(self):
        state = ExecState(run_id="run-1", total_nodes=4)
        assert state.run_id == "run-1"
        assert state.current_node is None
        assert state.completed == []
        assert state.finished is False
        assert state.progress == 0.0

    def test_progress_derived_from_completed_over_total(self):
        state = ExecState(run_id="run-1", total_nodes=4)
        state.completed.append(make_action_report())
        assert state.progress == 0.25
        state.completed.append(make_condition_report())
        state.completed.append(make_composite_report())
        assert state.progress == 0.75

    def test_finished_always_full_progress(self):
        state = ExecState(run_id="run-1", total_nodes=4, finished=True)
        assert state.progress == 1.0

    def test_unknown_total_progress_zero(self):
        state = ExecState(run_id="run-1")
        state.completed.append(make_action_report())
        assert state.progress == 0.0
