"""M8 任务 2.1 / 2.2（及 6.2）：截图写入存储目录、失败处理、节点记录不受影响。"""

from __future__ import annotations

import os

from autobranch.browser.models import PageRef
from reporting.factories import make_action_report, make_condition_report

from autobranch.reporting import Reporter


class TestCaptureScreenshot:
    """任务 2.1：调用 M1 截图能力、写入存储目录并返回路径。"""

    def test_screenshot_written_into_run_dir(self, tmp_path, fake_screenshotter):
        report_dir = tmp_path / "reports"
        reporter = Reporter("run-1", str(report_dir), screenshotter=fake_screenshotter)
        path = reporter.capture_screenshot(PageRef("1"), "点击登录")
        assert path
        assert os.path.isfile(path)
        assert path.startswith(str(report_dir))
        assert os.path.sep + "run-1" + os.path.sep in path
        with open(path, "rb") as handle:
            assert handle.read() == b"png-bytes"

    def test_screenshot_without_desc_default_name(self, tmp_path, fake_screenshotter):
        reporter = Reporter("run-1", str(tmp_path), screenshotter=fake_screenshotter)
        path = reporter.capture_screenshot(PageRef("1"))
        assert os.path.basename(path) == "001_shot.png"

    def test_screenshot_path_associated_with_node_report(self, tmp_path, fake_screenshotter):
        reporter = Reporter("run-1", str(tmp_path), screenshotter=fake_screenshotter)
        shot_path = reporter.capture_screenshot(PageRef("1"), "点击登录")
        report = make_action_report(screenshot_path=shot_path)
        reporter.record_node(report)
        assert reporter.exec_state().completed[0].screenshot_path == shot_path
        assert os.path.isfile(shot_path)

    def test_no_screenshotter_skips_gracefully(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path))
        assert reporter.capture_screenshot(PageRef("1")) == ""
        reporter.record_node(make_action_report())
        assert len(reporter.exec_state().completed) == 1


class TestScreenshotFailure:
    """任务 2.2：截图失败记录失败、返回空路径且不中断。"""

    def test_exception_returns_empty_path(self, tmp_path, failing_screenshotter):
        reporter = Reporter("run-1", str(tmp_path), screenshotter=failing_screenshotter)
        assert reporter.capture_screenshot(PageRef("1")) == ""

    def test_ok_false_returns_empty_path(self, tmp_path, error_screenshotter):
        reporter = Reporter("run-1", str(tmp_path), screenshotter=error_screenshotter)
        assert reporter.capture_screenshot(PageRef("1")) == ""

    def test_failure_does_not_affect_recorded_reports(self, tmp_path, failing_screenshotter):
        reporter = Reporter("run-1", str(tmp_path), screenshotter=failing_screenshotter)
        first = make_action_report(node_desc="先记录")
        reporter.record_node(first)
        shot = reporter.capture_screenshot(PageRef("1"), "失败截图")
        assert shot == ""
        second = make_action_report(node_desc="后记录", screenshot_path=shot)
        reporter.record_node(second)
        completed = reporter.exec_state().completed
        assert [r.node_desc for r in completed] == ["先记录", "后记录"]
        assert completed[1].screenshot_path == ""

    def test_failure_between_nodes_keeps_execution_flow(self, tmp_path, error_screenshotter):
        reporter = Reporter("run-1", str(tmp_path), screenshotter=error_screenshotter)
        reporter.record_node(make_action_report(node_desc="节点A"))
        assert reporter.capture_screenshot(PageRef("1")) == ""
        reporter.record_node(make_condition_report())
        assert len(reporter.exec_state().completed) == 2
