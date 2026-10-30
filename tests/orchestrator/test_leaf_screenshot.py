"""叶子节点执行后截图测试（traverser 仅对**浏览器叶子**在执行后拍当前页面）。

覆盖：浏览器叶子执行后拍当前页并记录**相对报告根**的截图路径；纯计算叶子
（used_browser=False，即使已开页）不截图；浏览器叶子无当前页时回落插件
semantic_graph 截图。
"""

from __future__ import annotations

import os

from autobranch.browser.models import OpResult, PageRef
from orchestrator_helpers import action, make_run_context

from autobranch.leaf_agent.models import LeafResult
from autobranch.orchestrator import RunConfig
from autobranch.orchestrator.traverser import Traverser
from autobranch.reporting import Reporter
from autobranch.reporting.models import LeafTrace


class _FakePage:
    def __init__(self, url: str = "http://example.com") -> None:
        self.url = url


class _FakeBrowserWithPage:
    """有当前页的假浏览器。"""

    def current_page(self):
        return PageRef("1")

    def page(self, ref):
        return OpResult(True, detail={"page": _FakePage()})


class _FakeBrowserNoPage:
    """无当前页的假浏览器。"""

    def current_page(self):
        return None


def _shot_writer(calls: list[str]):
    def _shot(page_ref, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(b"png-bytes")
        calls.append(path)
        return OpResult(True, detail={"path": path})

    return _shot


class _Leaf:
    """返回带 used_browser / screenshots 的叶子结果。"""

    def __init__(self, used_browser: bool = True, screenshots: tuple[str, ...] = ()) -> None:
        self._used_browser = used_browser
        self._screenshots = screenshots

    def __call__(self, node, timeout):
        return LeafResult(
            status="success",
            trace=LeafTrace(llm_input={"desc": node.description}),
            screenshots=self._screenshots,
            used_browser=self._used_browser,
        )


def test_browser_leaf_screenshot_after_node_relative_path(tmp_path):
    config = RunConfig(report_dir=str(tmp_path / "reports"))
    calls: list[str] = []
    reporter = Reporter(
        run_id="1", report_dir=config.report_dir, screenshotter=_shot_writer(calls)
    )
    ctx = make_run_context(
        config,
        leaf_executor=_Leaf(used_browser=True),
        browser=_FakeBrowserWithPage(),
        reporter=reporter,
    )
    Traverser(ctx).tick(action("点击登录按钮"))

    report = ctx.reporter.exec_state().completed[-1]
    assert calls, "浏览器叶子应在 tick 后调用截图器"
    assert report.screenshot_path
    assert not os.path.isabs(report.screenshot_path)
    assert report.screenshot_path.startswith("1/")
    assert os.path.isfile(os.path.join(config.report_dir, report.screenshot_path))
    assert report.page_url == "http://example.com"


def test_compute_leaf_no_screenshot_even_with_page(tmp_path):
    """纯计算叶子（used_browser=False）不开截图，即使已有页面也不截图、不写报告。"""
    config = RunConfig(report_dir=str(tmp_path / "reports"))
    calls: list[str] = []
    reporter = Reporter(
        run_id="1", report_dir=config.report_dir, screenshotter=_shot_writer(calls)
    )
    ctx = make_run_context(
        config,
        leaf_executor=_Leaf(used_browser=False),
        browser=_FakeBrowserWithPage(),
        reporter=reporter,
    )
    Traverser(ctx).tick(action("纯计算动作"))

    report = ctx.reporter.exec_state().completed[-1]
    assert calls == []
    assert report.screenshot_path is None
    assert report.page_url is None


def test_browser_leaf_fallback_to_plugin_screenshot_when_no_page(tmp_path):
    config = RunConfig(report_dir=str(tmp_path / "reports"))
    shot = tmp_path / "reports" / "1" / "semantic.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"png")

    reporter = Reporter(run_id="1", report_dir=config.report_dir)
    ctx = make_run_context(
        config,
        leaf_executor=_Leaf(used_browser=True, screenshots=(str(shot),)),
        browser=_FakeBrowserNoPage(),
        reporter=reporter,
    )
    Traverser(ctx).tick(action("看页面"))
    report = ctx.reporter.exec_state().completed[-1]
    assert report.screenshot_path == "1/semantic.png"
