"""引擎服务测试（任务 5.1）。

覆盖：mock 引擎可编程推进状态/失败；真实实现内嵌 M7（import 无错、mock
叶子下完整跑通并产出报告）。
"""

from __future__ import annotations

from pathlib import Path

from orchestrator_helpers import MockBrowser, StubLeaf

from autobranch.config import AutoBranchConfig
from autobranch.orchestrator import Engine
from autobranch.orchestrator.models import RunResult
from autobranch.reporting import ExecState
from autobranch.server.services.engine import (
    EmbeddedEngineService,
    EngineService,
    MockEngineService,
    build_reporter_factory,
)

from .conftest import VALID_YAML

# ------------------------------------------------------------- mock（5.1）

def test_mock_engine_returns_scripted_result():
    engine = MockEngineService()
    engine.set_script(1, result=RunResult(status="failure", failure_reason="脚本失败"))
    result = engine.run(tree_id=3, content="x", run_id=1)
    assert result.status == "failure"
    assert result.failure_reason == "脚本失败"
    assert engine.call_log == [(3, "x", 1)]


def test_mock_engine_advances_scripted_states():
    engine = MockEngineService()
    states = [
        ExecState(run_id="1", total_nodes=2, finished=False),
        ExecState(run_id="1", total_nodes=2, finished=True),
    ]
    engine.set_script(1, states=states)
    assert engine.get_exec_state(1).finished is False
    assert engine.get_exec_state(1).finished is True
    assert engine.get_exec_state(1) is None


def test_mock_engine_default_result():
    engine = MockEngineService()
    engine.default_result = RunResult(status="failure", failure_reason="兜底失败")
    result = engine.run(tree_id=1, content="x", run_id=9)
    assert result.failure_reason == "兜底失败"


# ------------------------------------------------------------- 真实内嵌（5.1）

def test_embedded_engine_is_engine_service():
    svc = EmbeddedEngineService(AutoBranchConfig.load(), Path("data/reports"))
    assert isinstance(svc, EngineService)


def test_embedded_engine_builds_default_engine():
    svc = EmbeddedEngineService(AutoBranchConfig.load(), Path("data/reports"))
    engine = svc._default_engine(1, Path("data/reports"))
    assert isinstance(engine, Engine)
    assert engine._registry is not None  # 插件模式（默认空注册表亦可）


def test_embedded_engine_runs_with_mock_leaf(tmp_path):
    report_root = tmp_path / "reports"

    def factory(run_id, report_root):
        return Engine(
            browser=MockBrowser(),
            leaf_executor=StubLeaf(),
            reporter_factory=build_reporter_factory(run_id, report_root),
        )

    svc = EmbeddedEngineService(
        AutoBranchConfig.load(), report_root, engine_factory=factory
    )
    result = svc.run(tree_id=1, content=VALID_YAML, run_id=7, doc_id="冒烟流程")
    assert result.status == "success"
    assert result.failure_reason is None
    assert (report_root / "7" / "exec_report.md").is_file()
    assert (report_root / "7" / "trace_report.md").is_file()

    state = svc.get_exec_state(7)
    assert state is not None
    assert state.finished is True
    assert state.progress == 1.0
    assert any(nr.node_type == "Action" for nr in state.completed)
