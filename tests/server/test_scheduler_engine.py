"""M10 调度引擎测试（依赖 DAG / 重试 / 错过补跑 / 来源标注）。"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

from autobranch.config import AutoBranchConfig
from autobranch.orchestrator.models import RunResult
from autobranch.scheduler.engine import SchedulerEngine
from autobranch.scheduler.models import ScheduleRule
from autobranch.server.db import configure_database, session_factory
from autobranch.server.models import Run, Tree
from autobranch.server.services.engine import EngineService, MockEngineService
from autobranch.server.services.runs import RunService

_TREE_TEMPLATE = (
    "tree: {name}\n"
    "nodes:\n"
    "  n1: {{type: Root, body: n2}}\n"
    "  n2: {{type: Action, description: 执行 {name}}}\n"
    "root: n1\n"
)


class FlakyEngine(EngineService):
    """首次失败、后续成功（用于验证立即重试）。"""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, tree_id, content, run_id, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return RunResult(status="failure", failure_reason="boom")
        return RunResult(status="success")

    def get_exec_state(self, run_id):
        return None


def _setup(tmp_path: Path, engine_service: EngineService | None = None):
    settings = tmp_path / "autobranch.db"
    configure_database(settings)
    report_root = tmp_path / "reports"
    report_root.mkdir()
    engine_service = engine_service or MockEngineService()
    run_service = RunService(engine_service, report_root, AutoBranchConfig())
    clock = [datetime(2026, 1, 1, 12, 0, 0)]
    scheduler = SchedulerEngine(run_service, tick_seconds=1, now=lambda: clock[0])
    run_service.set_on_run_complete(scheduler.on_run_complete)
    return run_service, scheduler, clock, engine_service


def _tree(name: str, *, status: str = "published") -> Tree:
    db = session_factory()()
    tree = Tree(
        name=name,
        content=_TREE_TEMPLATE.format(name=name),
        status=status,
    )
    db.add(tree)
    db.commit()
    db.refresh(tree)
    tree_id = tree.id
    db.close()
    return tree_id


def _add_rule(
    target_tree_id: int,
    *,
    dependencies: list[int] | None = None,
    last_run_at: datetime | None = None,
    on_failure: str = "immediate",
    max_retries: int = 2,
    retry_interval: int = 5,
    on_missed: str = "run",
) -> int:
    db = session_factory()()
    rule = ScheduleRule(
        name="rule",
        target_tree_id=target_tree_id,
        schedule_mode="interval",
        interval=1,
        interval_unit="days",
        dependencies=dependencies or [],
        on_failure=on_failure,
        max_retries=max_retries,
        retry_interval=retry_interval,
        on_missed=on_missed,
        inputs={},
        enabled=True,
        last_run_at=last_run_at,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    rule_id = rule.id
    db.close()
    return rule_id


def _runs() -> list[Run]:
    db = session_factory()()
    try:
        return db.query(Run).order_by(Run.id).all()
    finally:
        db.close()


def _wait_runs(count: int, timeout: float = 5.0) -> list[Run]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        runs = _runs()
        if len(runs) >= count and all(run.status in ("success", "failure") for run in runs):
            return runs
        time.sleep(0.02)
    return _runs()


def _wait_rule_status(rule_id: int, expected: str, timeout: float = 5.0) -> str | None:
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        db = session_factory()()
        try:
            rule = db.get(ScheduleRule, rule_id)
            status = rule.last_status if rule is not None else None
        finally:
            db.close()
        if status == expected:
            return status
        time.sleep(0.02)
    return status


def test_due_rule_triggers_schedule_run(tmp_path):
    run_service, scheduler, clock, _ = _setup(tmp_path)
    tree_id = _tree("目标")
    _add_rule(tree_id)

    scheduler.tick_once(clock[0])
    runs = _wait_runs(1)

    assert len(runs) == 1
    assert runs[0].source == "schedule"
    assert runs[0].status == "success"
    run_service.shutdown()


def test_dependency_runs_before_target(tmp_path):
    run_service, scheduler, clock, _ = _setup(tmp_path)
    dep_id = _tree("依赖")
    target_id = _tree("目标")
    _add_rule(target_id, dependencies=[dep_id])

    scheduler.tick_once(clock[0])
    runs = _wait_runs(2)

    assert [(run.tree_name_snapshot, run.source) for run in runs] == [
        ("依赖", "dependency"),
        ("目标", "schedule"),
    ]
    assert all(run.status == "success" for run in runs)
    run_service.shutdown()


def test_immediate_retry_after_failure(tmp_path):
    run_service, scheduler, clock, flaky = _setup(tmp_path, FlakyEngine())
    tree_id = _tree("目标")
    rule_id = _add_rule(tree_id, max_retries=2, retry_interval=5)

    scheduler.tick_once(clock[0])
    _wait_runs(1)
    assert _wait_rule_status(rule_id, "retrying") == "retrying"

    clock[0] = clock[0] + timedelta(seconds=5)
    scheduler.tick_once(clock[0])
    runs = _wait_runs(2)

    assert [run.status for run in runs] == ["failure", "success"]
    assert _wait_rule_status(rule_id, "success") == "success"
    run_service.shutdown()


def test_missed_schedule_skip_and_run(tmp_path):
    run_service, scheduler, clock, _ = _setup(tmp_path)
    tree_id = _tree("目标")
    skip_rule = _add_rule(
        tree_id,
        last_run_at=clock[0] - timedelta(days=2),
        on_missed="skip",
    )
    scheduler.tick_once(clock[0], startup=True)

    assert _runs() == []
    db = session_factory()()
    rule = db.get(ScheduleRule, skip_rule)
    assert rule.last_run_at == clock[0]
    assert rule.last_status == "skipped"
    db.close()

    run_rule = _add_rule(
        tree_id,
        last_run_at=clock[0] - timedelta(days=2),
        on_missed="run",
    )
    scheduler.tick_once(clock[0], startup=True)
    runs = _wait_runs(1)
    assert len(runs) == 1
    db = session_factory()()
    assert db.get(ScheduleRule, run_rule).last_run_at == clock[0]
    db.close()
    run_service.shutdown()
