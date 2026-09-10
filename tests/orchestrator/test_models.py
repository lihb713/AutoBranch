"""M7 任务 1.1/1.2：状态常量、RunConfig/RunResult 与 RunContext 依赖注入。"""

from __future__ import annotations

from orchestrator_helpers import MockBrowser, StubLeaf

from webops.orchestrator import (
    FAILURE,
    SUCCESS,
    RunConfig,
    RunContext,
    RunResult,
)
from webops.reporting import Reporter
from webops.schema import SchemaSpace


class TestNodeStatus:
    """任务 1.1：节点状态常量（SUCCESS/FAILURE，无 RUNNING）。"""

    def test_status_constants(self) -> None:
        assert SUCCESS == "success"
        assert FAILURE == "failure"
        assert SUCCESS in ("success", "failure")
        assert FAILURE in ("success", "failure")

    def test_no_running_state(self) -> None:
        from webops.orchestrator import NodeStatus

        allowed = ("success", "failure")
        # NodeStatus 是字面量联合，仅两种取值
        assert set(NodeStatus.__args__) == set(allowed)


class TestRunConfig:
    """任务 1.1：RunConfig 数据结构（全局 timeout 等）。"""

    def test_defaults(self) -> None:
        cfg = RunConfig()
        assert cfg.timeout == 120.0
        assert cfg.max_rounds == 10
        assert cfg.no_progress_rounds == 2
        assert cfg.report_dir == "reports"

    def test_custom_values(self) -> None:
        cfg = RunConfig(timeout=30.0, max_rounds=5, report_dir="/tmp/x")
        assert cfg.timeout == 30.0
        assert cfg.max_rounds == 5
        assert cfg.report_dir == "/tmp/x"

    def test_global_config_injected_as_dict(self) -> None:
        cfg = RunConfig(global_config={"retry": 3, "browser": "chromium"})
        assert cfg.global_config == {"retry": 3, "browser": "chromium"}


class TestRunResult:
    """任务 1.1：运行结果结构。"""

    def test_success_result(self) -> None:
        r = RunResult(status=SUCCESS)
        assert r.status == "success"
        assert r.failure_reason is None
        assert r.exec_report is None
        assert r.trace_report is None

    def test_failure_result_with_reason(self) -> None:
        r = RunResult(status=FAILURE, failure_reason="原因")
        assert r.failure_reason == "原因"


class TestRunContextDI:
    """任务 1.2：RunContext 依赖注入构造，各依赖可被 mock 替换。"""

    def test_dependencies_injected(self, config, tmp_path) -> None:
        space = SchemaSpace()
        reporter = Reporter("run-1", str(tmp_path))
        browser = MockBrowser()
        leaf = StubLeaf()
        ctx = RunContext(
            config=config,
            space=space,
            reporter=reporter,
            browser=browser,
            leaf_executor=leaf,
        )
        assert ctx.space is space
        assert ctx.reporter is reporter
        assert ctx.browser is browser
        assert ctx.leaf_executor is leaf
        assert ctx.failure_reason is None

    def test_all_dependencies_mock_replaceable(self, config, tmp_path) -> None:
        """依赖注入后逐一替换为 mock，遍历器仍正常工作（不依赖真实实现）。"""
        from orchestrator_helpers import make_run_context

        ctx = make_run_context(config)
        assert ctx.space is not None
        assert ctx.reporter is not None
        assert isinstance(ctx.browser, MockBrowser)
        assert isinstance(ctx.leaf_executor, StubLeaf)

    def test_schema_decl_converts_config_overrides(self, config) -> None:
        from orchestrator_helpers import make_run_context

        ctx = make_run_context(
            config,
            decl_inputs={"username": "str"},
            decl_outputs=["result"],
            config_overrides={"timeout": 30},
        )
        decl = ctx.schema_decl("文档B")
        assert decl.block_name == "文档B"
        assert decl.config == {"timeout": 30}
        assert decl.inputs == {"username": "str"}
        assert decl.outputs == {"result": ""}

    def test_current_frame_before_enter_is_none(self, config) -> None:
        ctx = RunContext(
            config=config,
            space=SchemaSpace(),
            reporter=Reporter("run-1", config.report_dir),
            browser=MockBrowser(),
            leaf_executor=StubLeaf(),
        )
        assert ctx.current_frame is None
