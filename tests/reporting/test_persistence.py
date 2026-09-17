"""M8 任务 5.1：按 run_id 归组的存储布局（截图/执行报告/回溯报告）。"""

from __future__ import annotations

import os

from autobranch.browser.models import PageRef
from reporting.factories import make_action_report

from autobranch.reporting import Reporter, sanitize_run_id


class TestRunDirLayout:
    """同一 run_id 下文件齐全、路径可被外部访问。"""

    def test_all_files_grouped_under_run_dir(self, tmp_path, fake_screenshotter):
        report_dir = tmp_path / "reports"
        reporter = Reporter("run-abc", str(report_dir), screenshotter=fake_screenshotter)
        shot = reporter.capture_screenshot(PageRef("1"), "点击登录")
        reporter.record_node(make_action_report(screenshot_path=shot))
        bundle = reporter.finalize()

        run_root = str(report_dir / "run-abc")
        assert reporter.run_root == run_root
        assert os.path.isdir(run_root)
        assert os.path.isfile(shot)
        assert shot.startswith(run_root)
        assert bundle.exec_report.path == os.path.join(run_root, "exec_report.md")
        assert bundle.trace_report.path == os.path.join(run_root, "trace_report.md")
        assert os.path.isfile(bundle.exec_report.path)
        assert os.path.isfile(bundle.trace_report.path)

        files = set(os.listdir(run_root))
        assert "exec_report.md" in files
        assert "trace_report.md" in files
        assert os.path.basename(shot) in files

    def test_files_accessible_externally(self, tmp_path, fake_screenshotter):
        reporter = Reporter("run-abc", str(tmp_path), screenshotter=fake_screenshotter)
        shot = reporter.capture_screenshot(PageRef("1"))
        reporter.record_node(make_action_report(screenshot_path=shot))
        bundle = reporter.finalize()
        with open(bundle.exec_report.path, encoding="utf-8") as handle:
            assert "点击登录" in handle.read()
        with open(bundle.trace_report.path, encoding="utf-8") as handle:
            assert "回溯报告" in handle.read()
        with open(shot, "rb") as handle:
            assert handle.read() == b"png-bytes"

    def test_screenshot_before_and_after_reports_share_run_dir(self, tmp_path, fake_screenshotter):
        report_dir = tmp_path / "reports"
        reporter = Reporter("run-1", str(report_dir), screenshotter=fake_screenshotter)
        first_shot = reporter.capture_screenshot(PageRef("1"), "节点A")
        reporter.record_node(make_action_report(screenshot_path=first_shot))
        second_shot = reporter.capture_screenshot(PageRef("2"), "节点B")
        reporter.record_node(make_action_report(node_desc="节点B", screenshot_path=second_shot))
        bundle = reporter.finalize()
        assert os.path.dirname(first_shot) == os.path.dirname(second_shot) == reporter.run_root
        assert os.path.isfile(bundle.exec_report.path)
        assert os.path.basename(first_shot) != os.path.basename(second_shot)


class TestRunIdIsolation:
    """不同 run_id 互不混淆。"""

    def test_different_run_ids_separate_dirs(self, tmp_path, fake_screenshotter):
        report_dir = tmp_path / "reports"
        reporter_a = Reporter("run-a", str(report_dir), screenshotter=fake_screenshotter)
        reporter_b = Reporter("run-b", str(report_dir), screenshotter=fake_screenshotter)
        shot_a = reporter_a.capture_screenshot(PageRef("1"))
        reporter_a.record_node(make_action_report(screenshot_path=shot_a))
        bundle_a = reporter_a.finalize()
        reporter_b.record_node(make_action_report(node_desc="另一个运行"))
        bundle_b = reporter_b.finalize()

        assert os.path.dirname(shot_a).endswith("run-a")
        assert os.path.basename(bundle_a.exec_report.path).startswith("exec_report")
        assert os.path.dirname(bundle_a.exec_report.path).endswith("run-a")
        assert os.path.dirname(bundle_b.exec_report.path).endswith("run-b")
        assert set(os.listdir(os.path.dirname(bundle_a.exec_report.path))) == {
            "exec_report.md",
            "trace_report.md",
            os.path.basename(shot_a),
        }
        assert set(os.listdir(os.path.dirname(bundle_b.exec_report.path))) == {
            "exec_report.md",
            "trace_report.md",
        }
        assert "另一个运行" in bundle_b.exec_report.text
        assert "另一个运行" not in bundle_a.exec_report.text

    def test_sanitize_run_id_unsafe_chars(self, tmp_path, fake_screenshotter):
        reporter = Reporter("run/1 : 我的流程", str(tmp_path), screenshotter=fake_screenshotter)
        shot = reporter.capture_screenshot(PageRef("1"))
        expected = sanitize_run_id("run/1 : 我的流程")
        assert "/" not in expected and " " not in expected and ":" not in expected
        assert "我的流程" not in expected
        assert reporter.run_root == str(tmp_path / expected)
        assert os.path.isfile(shot)
        assert reporter.run_id == "run/1 : 我的流程"
