"""M7 任务 4.3~4.5：会话初始化（全新 context + 全局配置注入根级 schema）与会话释放。"""

from __future__ import annotations

from orchestrator_helpers import MockBrowser, StubLeaf, action, leaf_failure

from autobranch.orchestrator import Engine, RunConfig
from autobranch.parser.models import BehaviorTree, SequenceNode
from autobranch.plugin_system import PluginBase, PluginRegistry
from autobranch.schema import SchemaSpace


def _tree() -> BehaviorTree:
    return BehaviorTree(
        name="主流程",
        root=SequenceNode(
            children=(action("动作"),),
        ),
    )


class TestSessionInit:
    """任务 4.3：浏览器冷启动懒装配（纯计算树零浏览器开销）；插件加载时启动全新 context。"""

    def test_run_pure_tree_does_not_start_browser(self, config, mock_browser, stub_leaf) -> None:
        engine = Engine(browser=mock_browser, leaf_executor=stub_leaf)
        result = engine.run(_tree(), config)
        assert result.status == "success"
        # 未使用浏览器插件 → 不冷启动驱动（懒装配，纯计算树零浏览器开销）
        assert mock_browser.starts == []

    def test_browser_plugin_load_starts_driver(self, config, mock_browser, stub_leaf) -> None:
        """浏览器插件懒装配（init）时冷启动驱动；release 后再次加载重新启动。"""
        import types

        from autobranch.plugins.browser import BrowserPlugin

        reg = PluginRegistry()
        reg.register(BrowserPlugin())
        runtime = types.SimpleNamespace(browser_factory=lambda: mock_browser)
        reg.ensure_loaded("browser", runtime)
        assert len(mock_browser.starts) == 1
        reg.release()
        reg.ensure_loaded("browser", runtime)
        assert len(mock_browser.starts) == 2

    def test_global_config_injected_to_root_schema(self, config) -> None:
        """任务 4.4：全局默认配置注入根级 schema，resolve_config 兜底可取到。"""
        space = SchemaSpace()
        engine = Engine(
            browser=MockBrowser(),
            leaf_executor=StubLeaf(),
            space_factory=lambda: space,
        )
        engine.run(_tree(), RunConfig(report_dir=config.report_dir, timeout=42.0))
        assert space.resolve_config(space.root, "timeout") == 42.0

    def test_global_config_extra_params(self, config) -> None:
        space = SchemaSpace()
        engine = Engine(
            browser=MockBrowser(),
            leaf_executor=StubLeaf(),
            space_factory=lambda: space,
        )
        engine.run(_tree(), RunConfig(report_dir=config.report_dir, global_config={"retry": 3}))
        assert space.resolve_config(space.root, "retry") == 3


class TestSessionRelease:
    """遍历结束统一释放插件资源（浏览器等由浏览器插件 release 负责）。"""

    def test_plugins_released_after_success(self, config, mock_browser, stub_leaf) -> None:
        released: list[str] = []

        class _P(PluginBase):
            name = "mock"

            def release(self):
                released.append("released")

        reg = PluginRegistry()
        reg.register(_P())
        reg.ensure_loaded("mock")
        engine = Engine(browser=mock_browser, leaf_executor=stub_leaf, registry=reg)
        engine.run(_tree(), config)
        assert released == ["released"]

    def test_plugins_released_after_failure(self, config, mock_browser, stub_leaf) -> None:
        released: list[str] = []

        class _P(PluginBase):
            name = "mock"

            def release(self):
                released.append("released")

        reg = PluginRegistry()
        reg.register(_P())
        reg.ensure_loaded("mock")
        stub_leaf.results["动作"] = leaf_failure("动作")
        engine = Engine(browser=mock_browser, leaf_executor=stub_leaf, registry=reg)
        result = engine.run(_tree(), config)
        assert result.status == "failure"
        assert released == ["released"]
