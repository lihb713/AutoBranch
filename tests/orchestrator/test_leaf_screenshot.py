"""叶子节点执行后截图测试（traverser 在叶子 tick 后拍当前页面）。

覆盖：浏览器叶子执行后拍当前页并记录**相对报告根**的截图路径；非浏览器叶子
（无当前页）不额外截图；无当前页时回落到插件 semantic_graph 截图。
"""

from __future__ import annotations

import os

from autobranch.browser.models import OpResult, PageRef
from orchestrator_helpers import StubLeaf, action, make_run_context

from autobranch.leaf_agent.models import LeafResult
from autobranch.orchestrator import RunConfig
from autobranch.orchestrator.traverser import Traverser
from autobranch.reporting import Reporter
from autobranch.reporting.models import LeafTrace


class _FakePage:
    def __init__(self, url: str = "http://example.com") -> None:
        self.url = url


class _FakeBrowserWithPage:
    """有当前页的假浏览器（模拟浏览器叶子执行后的页面）。"""

    def current_page(self):
        return PageRef("1")

    def page(self, ref):
        return OpResult(True, detail={"page": _FakePage()})


class _FakeBrowserNoPage:
    """无当前页的假浏览器（模拟非浏览器叶子）。"""

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


class _ShotLeaf:
    """返回带 screenshots 的叶子结果（模拟浏览器插件 semantic_graph 截图）。"""

    def __init__(self, shot: str) -> None:
        self._shot = shot

    def __call__(self, node, timeout):
        return LeafResult(
            status="success",
            trace=LeafTrace(llm_input={"desc": node.description}),
            screenshots=(self._shot,),
        )


def test_leaf_screenshot_after_node_with_relative_path(tmp_path):
    config = RunConfig(report_dir=str(tmp_path / "reports"))
    calls: list[str] = []
    reporter = Reporter(
        run_id="1", report_dir=config.report_dir, screenshotter=_shot_writer(calls)
    )
    ctx = make_run_context(
        config, leaf_executor=StubLeaf(), browser=_FakeBrowserWithPage(), reporter=reporter
    )
    Traverser(ctx).tick(action("点击登录按钮"))

    report = ctx.reporter.exec_state().completed[-1]
    # 节点执行后拍了当前页
    assert calls, "应在叶子 tick 后调用截图器"
    # 截图路径为相对报告根（供前端 /api/reports/{path} 提供）
    assert report.screenshot_path
    assert not os.path.isabs(report.screenshot_path)
    assert report.screenshot_path.startswith("1/")
    assert os.path.isfile(os.path.join(config.report_dir, report.screenshot_path))
    # 页面 URL 一并记录
    assert report.page_url == "http://example.com"


def test_no_current_page_no_extra_screenshot(tmp_path):
    config = RunConfig(report_dir=str(tmp_path / "reports"))
    calls: list[str] = []
    reporter = Reporter(
        run_id="1", report_dir=config.report_dir, screenshotter=_shot_writer(calls)
    )
    ctx = make_run_context(
        config, leaf_executor=StubLeaf(), browser=_FakeBrowserNoPage(), reporter=reporter
    )
    Traverser(ctx).tick(action("纯计算动作"))

    report = ctx.reporter.exec_state().completed[-1]
    assert calls == []  # 非浏览器叶子不额外截图
    assert report.screenshot_path is None


def test_fallback_to_plugin_screenshot_when_no_current_page(tmp_path):
    config = RunConfig(report_dir=str(tmp_path / "reports"))
    shot = tmp_path / "reports" / "1" / "semantic.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"png")

    # reporter 无截图器 → 不会拍当前页；无当前页 → 回落插件截图
    reporter = Reporter(run_id="1", report_dir=config.report_dir)
    ctx = make_run_context(
        config,
        leaf_executor=_ShotLeaf(str(shot)),
        browser=_FakeBrowserNoPage(),
        reporter=reporter,
    )
    Traverser(ctx).tick(action("看页面"))
    report = ctx.reporter.exec_state().completed[-1]
    assert report.screenshot_path == "1/semantic.png"
