"""RunService 队列调度定向测试（Change A 任务 3.2）。

覆盖：并发上限、FIFO 顺序、完成自动调度下一个。用阻塞 mock 引擎保证确定性。
"""

from __future__ import annotations

import threading
import time

from autobranch.config import AutoBranchConfig
from autobranch.orchestrator.models import RunResult
from autobranch.server.db import configure_database, session_factory
from autobranch.server.models import Run, Tree
from autobranch.server.services.engine import EngineService
from autobranch.server.services.runs import RunService

from .conftest import make_tree_yaml


class BlockingEngine(EngineService):
    """mock 引擎：run 阻塞直到 release，记录调用顺序。"""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls: list[int] = []

    def run(self, tree_id, content, run_id, *, doc_id=None, run_inputs=None):
        self.calls.append(run_id)
        self.started.set()
        self.release.wait()
        return RunResult(status="success")

    def get_exec_state(self, run_id):
        return None


def _service(tmp_path, max_concurrent=1) -> tuple[RunService, BlockingEngine]:
    engine = BlockingEngine()
    service = RunService(
        engine, tmp_path / "reports", AutoBranchConfig(max_concurrent_runs=max_concurrent)
    )
    configure_database(tmp_path / "autobranch.db")
    return service, engine


def test_concurrency_cap_and_fifo_and_auto_drain(tmp_path):
    service, engine = _service(tmp_path, max_concurrent=1)
    db = session_factory()()
    tree = Tree(name="t", content=make_tree_yaml("t"))
    db.add(tree)
    db.commit()
    db.refresh(tree)

    r1 = service.start(db, tree.id)
    assert engine.started.wait(timeout=5) is True  # r1 立即执行
    r2 = service.start(db, tree.id)
    r3 = service.start(db, tree.id)
    assert db.get(Run, r2.id).status == "pending"  # 并发满进排队
    assert db.get(Run, r3.id).status == "pending"

    engine.release.set()  # r1 完成 → 自动调度 r2
    deadline = time.time() + 5
    while time.time() < deadline:
        db.expire_all()
        if db.get(Run, r2.id).status != "pending":
            break
        time.sleep(0.05)
    assert db.get(Run, r2.id).status != "pending"  # r2 已自动开始

    engine.release.set()  # r2 完成 → 调度 r3
    deadline = time.time() + 5
    while time.time() < deadline:
        db.expire_all()
        if db.get(Run, r3.id).status != "pending":
            break
        time.sleep(0.05)
    assert db.get(Run, r3.id).status != "pending"

    # FIFO 顺序：calls 顺序 = 提交顺序
    assert engine.calls == [r1.id, r2.id, r3.id]
    db.close()
    service.shutdown()


def test_queued_run_restarts_as_interrupted(tmp_path):
    """排队中（pending）实例在"重启"时被 mark_interrupted 置 failure。"""
    service, engine = _service(tmp_path, max_concurrent=1)
    db = session_factory()()
    tree = Tree(name="t", content=make_tree_yaml("t"))
    db.add(tree)
    db.commit()
    db.refresh(tree)
    run = Run(
        tree_id=tree.id,
        status="pending",
        content_snapshot=tree.content,
        tree_name_snapshot="t",
        tree_content_hash="h",
    )
    db.add(run)
    db.commit()
    run_id = run.id
    db.close()

    count = RunService.mark_interrupted()
    assert count == 1
    fresh = session_factory()()
    assert fresh.get(Run, run_id).status == "failure"
    assert fresh.get(Run, run_id).failure_reason == "interrupted"
    fresh.close()
    service.shutdown()
