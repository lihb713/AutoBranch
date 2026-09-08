"""M8 任务 3.1 / 3.2 / 3.3（及 6.1 / 6.3）：两份报告生成与 finalize 打包。"""

from __future__ import annotations

import os

from reporting.factories import (
    TIMESTAMP,
    URL,
    make_action_report,
    make_composite_report,
    make_condition_report,
)

from webops.browser.models import PageRef
from webops.reporting import Reporter
from webops.reporting.models import ActionCall


class TestExecReport:
    """任务 3.1：执行报告每节点输出类型/描述/结果/函数调用/判断结果/时间/URL/截图。

    执行报告不含 LLM 推理。
    """

    def _build_reporter(self, tmp_path, screenshotter=None):
        reporter = Reporter("run-1", str(tmp_path), screenshotter=screenshotter, total_nodes=3)
        shot = reporter.capture_screenshot(PageRef("1"), "点击登录") if screenshotter else ""
        reporter.record_node(make_action_report(screenshot_path=shot))
        reporter.record_node(make_condition_report(node_desc="工作台可见"))
        reporter.record_node(make_composite_report(node_desc="登录流程"))
        return reporter

    def test_exec_report_contains_each_node_fields(self, tmp_path, fake_screenshotter):
        reporter = self._build_reporter(tmp_path, fake_screenshotter)
        text = reporter.finalize().exec_report.text
        assert "执行情况报告" in text
        assert "运行标识: run-1" in text
        assert "节点数: 3" in text
        assert "点击登录" in text and "SUCCESS" in text
        assert "节点类型: Action" in text
        assert "函数调用: click（成功）" in text
        assert "判断结果: 是" in text
        assert TIMESTAMP in text
        assert URL in text
        shot_path = reporter.exec_state().completed[0].screenshot_path
        assert shot_path and os.path.isfile(shot_path)
        # 截图以 Markdown 图片语法输出（相对文件名，与报告同目录）
        filename = os.path.basename(shot_path)
        assert f"![节点截图: 点击登录]({filename})" in text

    def test_exec_report_lists_failure_nodes(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path))
        reporter.record_node(make_action_report(node_desc="点击登录", result="failure"))
        text = reporter.finalize().exec_report.text
        assert "FAILURE" in text

    def test_exec_report_excludes_llm_reasoning(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path))
        reporter.record_node(make_action_report())
        text = reporter.finalize().exec_report.text
        assert "LLM 输入" not in text
        assert "LLM 推理过程" not in text
        assert "LLM 决策结果" not in text
        assert "semantic_graph" not in text

    def test_exec_report_no_screenshot_line_for_composite(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path))
        reporter.record_node(make_composite_report(node_desc="登录流程"))
        text = reporter.finalize().exec_report.text
        assert "截图:" not in text


class TestTraceReport:
    """任务 3.2 / 6.3：回溯报告含 LLM 输入/推理过程/决策结果，不含截图。"""

    def test_trace_report_contains_llm_sections(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path))
        reporter.record_node(make_action_report())
        reporter.record_node(make_composite_report(node_desc="登录流程"))
        text = reporter.finalize().trace_report.text
        assert "回溯报告" in text
        assert "LLM 输入:" in text
        assert "node_desc: 点击登录" in text
        assert "semantic_graph: graph-1" in text
        assert "LLM 推理过程:" in text
        assert "- 选择函数 click" in text
        assert "LLM 决策结果: 调用 click 点击 #login" in text
        assert "工具调用序列:" in text
        assert "click（成功）" in text

    def test_trace_report_excludes_screenshot(self, tmp_path, fake_screenshotter):
        reporter = Reporter("run-1", str(tmp_path), screenshotter=fake_screenshotter)
        shot = reporter.capture_screenshot(PageRef("1"), "点击登录")
        reporter.record_node(make_action_report(screenshot_path=shot))
        text = reporter.finalize().trace_report.text
        assert shot not in text
        assert "截图" not in text

    def test_trace_report_node_without_trace_keeps_detail(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path))
        reporter.record_node(make_composite_report(node_desc="登录流程"))
        reporter.record_node(make_action_report())
        text = reporter.finalize().trace_report.text
        assert "登录流程" in text and "SUCCESS" in text
        assert "节点描述: 登录流程" in text
        assert text.count("LLM 输入:") == 1

    def test_trace_report_reasoning_after_failure(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path))
        reporter.record_node(make_action_report(result="failure"))
        text = reporter.finalize().trace_report.text
        assert "FAILURE" in text
        assert "LLM 推理过程:" in text


class TestFinalizeBundle:
    """任务 3.3：finalize 返回 ReportBundle，两份报告内容一致、均落盘。"""

    def test_finalize_returns_bundle_with_both_reports(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path), total_nodes=2)
        reporter.record_node(make_action_report())
        reporter.record_node(make_condition_report(node_desc="工作台可见"))
        bundle = reporter.finalize()
        assert bundle.exec_report.run_id == "run-1"
        assert bundle.trace_report.run_id == "run-1"
        assert "点击登录" in bundle.exec_report.text
        assert "点击登录" in bundle.trace_report.text
        assert bundle.exec_report.path and os.path.isfile(bundle.exec_report.path)
        assert bundle.trace_report.path and os.path.isfile(bundle.trace_report.path)

    def test_two_reports_from_same_node_set(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path), total_nodes=3)
        reporter.record_node(make_action_report(node_desc="节点A"))
        reporter.record_node(make_condition_report(node_desc="节点B"))
        reporter.record_node(make_composite_report(node_desc="节点C"))
        bundle = reporter.finalize()
        for text in (bundle.exec_report.text, bundle.trace_report.text):
            assert text.count("节点描述: 节点A") == 1
            assert text.count("节点描述: 节点B") == 1
            assert text.count("节点描述: 节点C") == 1
            assert text.count("[3]") == 1

    def test_finalize_persists_report_files(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path))
        reporter.record_node(make_action_report())
        bundle = reporter.finalize()
        with open(bundle.exec_report.path, encoding="utf-8", newline="") as handle:
            assert handle.read() == bundle.exec_report.text
        with open(bundle.trace_report.path, encoding="utf-8", newline="") as handle:
            assert handle.read() == bundle.trace_report.text


class TestMixedNodeScenario:
    """任务 6.1：覆盖 Action/Condition/复合节点、成功/失败的节点报告集。"""

    def test_mixed_nodes_two_reports_correct(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path), total_nodes=4)
        reporter.record_node(make_action_report(node_desc="点击登录"))
        reporter.record_node(
            make_action_report(
                node_desc="输入密码",
                result="failure",
                action_call=ActionCall("type", False, error="元素不可见"),
                llm_trace=None,
            )
        )
        reporter.record_node(make_condition_report(node_desc="工作台可见"))
        reporter.record_node(make_composite_report(node_desc="登录流程", result="failure"))
        bundle = reporter.finalize()
        exec_text = bundle.exec_report.text
        assert exec_text.count("结果: SUCCESS") == 2
        assert exec_text.count("结果: FAILURE") == 2
        assert "函数调用: click（成功）" in exec_text
        assert "函数调用: type（失败）" in exec_text
        assert "判断结果: 是" in exec_text
        trace_text = bundle.trace_report.text
        assert trace_text.count("结果: FAILURE") == 2
        assert "LLM 推理过程:" in trace_text
