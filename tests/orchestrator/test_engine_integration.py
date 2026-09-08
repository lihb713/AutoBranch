"""M7 任务 1.4 / 6.1 / 6.2：引擎入口与集成冒烟（mock 叶子 + 真实浏览器可选）。"""

from __future__ import annotations

import pytest
from orchestrator_helpers import (
    StubLeaf,
    action,
    branch,
    cond,
    leaf_condition,
    leaf_failure,
    leaf_success,
    repeat,
    sel,
    seq,
)

from webops.orchestrator import Engine, RunConfig
from webops.parser.models import BehaviorTree


def _tree() -> BehaviorTree:
    return BehaviorTree(
        name="主流程",
        root=seq(action("动作")),
    )


class TestEngineRun:
    """任务 1.4：Engine.run 入口——解析校验 → 会话初始化 → 遍历 → RunResult。"""

    def test_run_returns_run_result_with_reports(self, config, mock_browser, stub_leaf) -> None:
        engine = Engine(browser=mock_browser, leaf_executor=stub_leaf)
        result = engine.run(_tree(), {}, config)
        assert result.status == "success"
        assert result.failure_reason is None
        assert result.exec_report is not None
        assert result.trace_report is not None
        assert result.exec_report.path.endswith("exec_report.md")
        assert result.trace_report.path.endswith("trace_report.md")

    def test_validation_failure_no_traversal(self, config, mock_browser, stub_leaf) -> None:
        """校验失败：返回修正信息，不启动会话/遍历/报告。"""
        engine = Engine(browser=mock_browser, leaf_executor=stub_leaf)
        result = engine.run(None, {}, config)
        assert result.status == "failure"
        assert "行为树为空" in result.failure_reason
        assert result.exec_report is None
        assert result.trace_report is None
        assert len(mock_browser.starts) == 0
        assert len(stub_leaf.calls) == 0

    def test_validation_missing_config(self, mock_browser, stub_leaf) -> None:
        engine = Engine(browser=mock_browser, leaf_executor=stub_leaf)
        result = engine.run(_tree(), {}, None)
        assert result.status == "failure"
        assert "运行配置缺失" in result.failure_reason
        assert len(mock_browser.starts) == 0

    def test_validation_wrong_config_type(self, mock_browser, stub_leaf) -> None:
        engine = Engine(browser=mock_browser, leaf_executor=stub_leaf)
        result = engine.run(_tree(), {}, {"timeout": 1})
        assert result.status == "failure"
        assert "运行配置类型非法" in result.failure_reason
        assert len(mock_browser.starts) == 0

    def test_run_failure_reason_points_to_leaf(self, config, mock_browser, stub_leaf) -> None:
        stub_leaf.results["动作"] = leaf_failure("动作", terminator="no_progress")
        engine = Engine(browser=mock_browser, leaf_executor=stub_leaf)
        result = engine.run(_tree(), {}, config)
        assert result.status == "failure"
        assert result.failure_reason is not None
        assert "动作" in result.failure_reason
        assert result.exec_report is not None  # 遍历启动后仍产出报告


class TestEngineEndToEnd:
    """任务 6.1：跨 Sequence/Selector/Repeat/块引用/失败路径的 mock 树端到端聚合。"""

    def test_success_path_aggregation(self, config, mock_browser) -> None:
        leaf = StubLeaf()
        leaf.results.update(
            {
                "打开页面": leaf_success("打开页面"),
                "填用户名": leaf_success("填用户名"),
                "用户名已填": leaf_condition(True, "用户名已填"),
                "已登录": leaf_condition(False, "已登录"),
                "进入工作台": leaf_success("进入工作台"),
                "登录页停留": leaf_success("登录页停留"),
                "刷新页面": [
                    leaf_failure("刷新页面"),
                    leaf_failure("刷新页面"),
                    leaf_success("刷新页面"),
                ],
                "最终状态OK": leaf_condition(True, "最终状态OK"),
            }
        )
        engine = Engine(browser=mock_browser, leaf_executor=leaf)
        tree = BehaviorTree(
            name="主流程",
            root=seq(
                action("打开页面"),
                seq(
                    action("填用户名"),
                    cond("用户名已填"),
                ),
                sel(
                    branch(cond("已登录"), action("进入工作台")),
                    branch(None, action("登录页停留")),
                ),
                repeat(action("刷新页面"), mode="retry", max=3),
                cond("最终状态OK"),
            ),
        )
        result = engine.run(tree, {}, config)
        assert result.status == "success"
        assert result.failure_reason is None
        final = engine.get_exec_state()
        assert final.finished is True
        descs = [r.node_desc for r in final.completed]
        # 嵌套子序列、retry 叶子、otherwise 分支叶子均执行
        assert "填用户名" in descs
        assert "刷新页面" in descs
        assert "登录页停留" in descs
        # 未命中分支不执行
        assert "进入工作台" not in descs
        # Selector 条件"已登录"失败 → 记失败报告
        assert any(r.node_desc == "已登录" and r.result == "failure" for r in final.completed)
        # Retry 执行 3 轮（2 失败 + 1 成功）
        refresh_reports = [r for r in final.completed if r.node_desc == "刷新页面"]
        assert len(refresh_reports) == 3

    def test_failure_path_aggregation(self, config, mock_browser) -> None:
        leaf = StubLeaf()
        leaf.results.update(
            {"ok": leaf_success("ok"), "bad": leaf_failure("bad"), "ok2": leaf_success("ok2")}
        )
        engine = Engine(browser=mock_browser, leaf_executor=leaf)
        tree = BehaviorTree(
            name="主流程",
            root=seq(action("ok"), action("bad"), action("ok2")),
        )
        result = engine.run(tree, {}, config)
        assert result.status == "failure"
        assert "bad" in result.failure_reason
        assert result.exec_report is not None
        # 短路：ok2 不执行
        assert "ok2" not in [r.node_desc for r in engine.get_exec_state().completed]

    def test_repeat_max_reaches_failure(self, config, mock_browser) -> None:
        leaf = StubLeaf()
        leaf.results["总是失败"] = leaf_failure("总是失败")
        engine = Engine(browser=mock_browser, leaf_executor=leaf)
        tree = BehaviorTree(
            name="主流程",
            root=seq(repeat(action("总是失败"), mode="retry", max=2)),
        )
        result = engine.run(tree, {}, config)
        assert result.status == "failure"
        assert result.failure_reason is not None


@pytest.mark.integration
class TestRealBrowserSmoke:
    """任务 6.2（可选）：真实小行为树 + 真实浏览器跑通——验证超时/截图/报告链路。"""

    def test_real_browser_open_and_screenshot(self, config) -> None:
        from webops.browser import BrowserDriver
        from webops.leaf_agent.models import LeafResult
        from webops.reporting.models import LeafTrace
        from webops.schema import SchemaSpace
        from webops.schema.models import PageRef as SchemaPageRef

        browser = BrowserDriver()
        space = SchemaSpace()
        captured = {}

        def leaf(node, timeout):
            if node.description == "打开测试页":
                op = browser.open("data:text/html,<h1>M7 冒烟</h1>")
                assert op.ok, op.error
                ref = op.detail["page_ref"]
                space.write(
                    space._current,
                    "$this/page",
                    SchemaPageRef(page_id=ref.id, url=op.detail.get("url", "")),
                    "page_ref",
                )
                return LeafResult(
                    status="success", trace=LeafTrace(llm_input={"d": node.description})
                )
            if node.description == "页面已打开":
                page = space.current_page(space._current)
                captured["page"] = page
                return LeafResult(
                    status="success" if page else "failure",
                    bool_value=bool(page),
                    trace=LeafTrace(llm_input={}),
                )
            return LeafResult(status="success", trace=LeafTrace(llm_input={"d": node.description}))

        engine = Engine(
            browser=browser,
            space_factory=lambda: space,
            leaf_executor=leaf,
        )
        tree = BehaviorTree(
            name="主流程",
            root=seq(
                action("打开测试页"),
                cond("页面已打开"),
            ),
        )
        result = engine.run(tree, {}, RunConfig(report_dir=config.report_dir))
        assert result.status == "success"
        assert captured["page"] is not None
        # 截图链路：Action 返回前经 M1 截图落盘，NodeReport 携带路径
        final = engine.get_exec_state()
        action_report = [r for r in final.completed if r.node_type == "Action"][0]
        assert action_report.screenshot_path
        assert action_report.page_url
