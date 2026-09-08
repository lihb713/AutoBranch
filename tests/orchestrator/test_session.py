"""M7 任务 4.3~4.5：会话初始化（全新 context + 全局配置注入根级 schema）与会话释放。"""

from __future__ import annotations

from orchestrator_helpers import MockBrowser, StubLeaf, action, leaf_failure

from webops.orchestrator import Engine, RunConfig
from webops.parser.models import BehaviorTree, SequenceNode
from webops.schema import SchemaSpace


def _tree() -> BehaviorTree:
    return BehaviorTree(
        name="主流程",
        root=SequenceNode(
            children=(action("动作", frame="主流程/"),),
            frame="主流程/",
        ),
    )


class TestSessionInit:
    """任务 4.3：每次 run 创建全新浏览器 context（无持久化）。"""

    def test_run_starts_fresh_context(self, config, mock_browser, stub_leaf) -> None:
        engine = Engine(browser=mock_browser, leaf_executor=stub_leaf)
        result = engine.run(_tree(), {}, config)
        assert result.status == "success"
        # start 每次调用都会先 stop 再新建 context（M1 冷启动语义），M7 每 run 必调
        assert len(mock_browser.starts) == 1

    def test_each_run_starts_new_context(self, config, mock_browser, stub_leaf) -> None:
        engine = Engine(browser=mock_browser, leaf_executor=stub_leaf)
        engine.run(_tree(), {}, config)
        engine.run(_tree(), {}, config)
        # 两次 run = start/stop/start/stop，无运行间残留
        assert len(mock_browser.starts) == 2
        assert len(mock_browser.stops) == 2
        assert mock_browser.started is False  # 上次运行后已释放

    def test_global_config_injected_to_root_schema(self, config) -> None:
        """任务 4.4：全局默认配置注入根级 schema，resolve_config 兜底可取到。"""
        space = SchemaSpace()
        engine = Engine(
            browser=MockBrowser(),
            leaf_executor=StubLeaf(),
            space_factory=lambda: space,
        )
        engine.run(_tree(), {}, RunConfig(report_dir=config.report_dir, timeout=42.0))
        assert space.resolve_config(space.root, "timeout") == 42.0

    def test_global_config_extra_params(self, config) -> None:
        space = SchemaSpace()
        engine = Engine(
            browser=MockBrowser(),
            leaf_executor=StubLeaf(),
            space_factory=lambda: space,
        )
        engine.run(_tree(), {}, RunConfig(report_dir=config.report_dir, global_config={"retry": 3}))
        assert space.resolve_config(space.root, "retry") == 3


class TestSessionRelease:
    """任务 4.5：遍历结束（成功/失败）统一关闭 context，运行间无残留。"""

    def test_browser_stopped_after_success(self, config, mock_browser, stub_leaf) -> None:
        engine = Engine(browser=mock_browser, leaf_executor=stub_leaf)
        engine.run(_tree(), {}, config)
        assert len(mock_browser.stops) == 1
        assert mock_browser.started is False

    def test_browser_stopped_after_failure(self, config, mock_browser, stub_leaf) -> None:
        stub_leaf.results["动作"] = leaf_failure("动作")
        engine = Engine(browser=mock_browser, leaf_executor=stub_leaf)
        result = engine.run(_tree(), {}, config)
        assert result.status == "failure"
        assert len(mock_browser.stops) == 1
        assert mock_browser.started is False
