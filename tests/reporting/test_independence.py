"""M8 任务 6.5：独立性验证。

全部测试仅 mock M1/M6/M7 数据，不启动真实浏览器与 LLM；除 ``pytest -m
integration`` 标记的真实截图用例外，本模块与单元测试不依赖任何真实执行环境。
"""

from __future__ import annotations

import inspect
import sys

from reporting.factories import make_action_report, make_composite_report, make_condition_report

from webops.browser.models import PageRef
from webops.reporting import Reporter
from webops.reporting.models import NodeInfo


class TestIndependence:
    """mock M1/M6/M7 数据下全流程可用，无需真实浏览器/LLM。"""

    def test_reporting_source_has_no_playwright_dependency(self):
        names = (
            "webops.reporting.models",
            "webops.reporting.render",
            "webops.reporting.reporter",
        )
        for name in names:
            source = inspect.getsource(sys.modules[name])
            assert "playwright" not in source, f"{name} 不应依赖 playwright"

    def test_full_flow_without_browser(self, tmp_path):
        reporter = Reporter("run-1", str(tmp_path), total_nodes=3)
        reporter.start_node(NodeInfo(node_type="Sequence", node_desc="登录流程"))
        reporter.record_node(make_action_report(node_desc="点击登录"))
        reporter.record_node(make_condition_report(node_desc="工作台可见"))
        reporter.record_node(make_composite_report(node_desc="登录流程"))
        assert reporter.capture_screenshot(PageRef("1")) == ""
        bundle = reporter.finalize()
        state = reporter.exec_state()
        assert state.finished is True
        assert state.progress == 1.0
        assert "点击登录" in bundle.exec_report.text
        assert "LLM 推理过程:" in bundle.trace_report.text
