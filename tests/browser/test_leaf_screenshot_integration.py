"""真实浏览器：引擎叶子执行后截图的端到端验证（integration）。

用一个真实浏览器 + mock 叶子执行器（打开本地页并点击登录，改变页面状态）跑引擎，
断言节点报告携带**相对报告根**的截图路径、文件真实落盘、且 page_url 为操作后的页面。
"""

from __future__ import annotations

import os

import pytest
from orchestrator_helpers import action, leaf_success

from autobranch.browser import BrowserConfig, BrowserDriver, ElementRef
from autobranch.orchestrator import Engine, RunConfig
from autobranch.parser.models import BehaviorTree

pytestmark = pytest.mark.integration


def test_engine_post_node_screenshot_real_browser(tmp_path, server_url):
    driver = BrowserDriver()
    driver.start(BrowserConfig(headless=True, timeout_ms=5000))

    def leaf(node, timeout):
        # 模拟浏览器叶子：打开页面 → 点击"登录"按钮（页面状态改变）
        opened = driver.open(f"{server_url}/basic.html")
        assert opened.ok, opened.error
        handle = driver.page(opened.detail["page_ref"]).detail["page"]
        clicked = handle.click(ElementRef("#login-btn"))
        assert clicked.ok, clicked.error
        return leaf_success(node.description)

    try:
        engine = Engine(browser=driver, leaf_executor=leaf)
        config = RunConfig(report_dir=str(tmp_path / "reports"))
        result = engine.run(BehaviorTree(name="主流程", root=action("登录")), config)
        assert result.status == "success"

        completed = engine.get_exec_state().completed
        reports = [r for r in completed if r.node_type == "Action"]
        assert reports
        report = reports[-1]
        # 节点执行后截图：相对报告根、文件真实落盘
        assert report.screenshot_path
        assert not os.path.isabs(report.screenshot_path)
        assert os.path.isfile(os.path.join(config.report_dir, report.screenshot_path))
        # page_url 为操作后的页面（basic.html）
        assert report.page_url and report.page_url.endswith("basic.html")
    finally:
        driver.stop()
