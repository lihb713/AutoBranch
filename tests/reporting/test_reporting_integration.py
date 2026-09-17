"""M8 真实截图集成测试：经 M1 真实浏览器截图并关联到报告（验收标准 §6）。

该用例属于 ``pytest -m integration``，其余单元测试不依赖真实浏览器/LLM。
"""

from __future__ import annotations

import os

import pytest
from autobranch.browser.models import PageRef
from reporting.factories import make_action_report

from autobranch.browser import BrowserConfig, BrowserDriver
from autobranch.reporting import Reporter

pytestmark = pytest.mark.integration

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_reporter_captures_real_browser_screenshot(tmp_path):
    driver = BrowserDriver()
    driver.start(BrowserConfig(timeout_ms=5000))
    try:
        result = driver.open("data:text/html,<html><body><h1>AutoBranch</h1></body></html>")
        assert result.ok, result.error
        page_ref = result.detail["page_ref"]

        def shot(ref: PageRef, path: str):
            return driver.page(ref).detail["page"].screenshot(path)

        reporter = Reporter("run-int", str(tmp_path / "reports"), screenshotter=shot)
        shot_path = reporter.capture_screenshot(page_ref, "标题")
        assert shot_path
        assert os.path.isfile(shot_path)
        with open(shot_path, "rb") as handle:
            assert handle.read(8) == PNG_SIGNATURE

        reporter.record_node(make_action_report(screenshot_path=shot_path))
        bundle = reporter.finalize()
        filename = os.path.basename(shot_path)
        assert f"![节点截图: 点击登录]({filename})" in bundle.exec_report.text
        assert shot_path not in bundle.trace_report.text
        assert os.path.isfile(bundle.exec_report.path)
    finally:
        driver.stop()
