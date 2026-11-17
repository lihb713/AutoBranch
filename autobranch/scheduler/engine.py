"""M10 调度引擎（后台守护线程 + 依赖 DAG + 重试 + 错过补跑）。

设计要点：
- 只做“何时触发 + 依赖顺序”，实际执行统一交给 ``RunService.start``；
- ``RunService`` 执行完成回调 ``on_run_complete`` 唤醒引擎，更新依赖状态；
- 等待队列/执行队列保存在内存，进程重启后按 ``last_run_at`` 重新判断错过；
- 同一棵树的前置依赖同时只触发一个执行，避免依赖风暴。
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from autobranch.scheduler.models import ScheduleRule
from autobranch.scheduler.timecalc import calculate_next_run
from autobranch.server.db import session_factory
from autobranch.server.errors import AppError
from autobranch.server.models import Run, Tree
from autobranch.server.services.runs import RunService, validate_run_inputs

logger = logging.getLogger(__name__)


@dataclass
class _Task:
    """一次待执行的调度任务（目标或前置依赖）。"""

    id: int
    kind: str  # "schedule" | "dependency"
    rule_id: int | None
    target_tree_id: int
    dependencies: list[int]
    inputs: dict
    source: str
    created_at: datetime
    on_failure: str = "next_schedule"
    max_retries: int = 0
    retry_interval: int = 60
    retry_count: int = 0
    next_attempt_at: datetime | None = None
    satisfied: set[int] = field(default_factory=set)
    run_id: int | None = None


class SchedulerEngine:
    """单线程调度器；测试可注入 ``now`` 与直接调用 ``tick_once``。"""

    def __init__(
        self,
        run_service: RunService,
        *,
        tick_seconds: float = 10.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._run_service = run_service
        self._tick_seconds = max(0.1, float(tick_seconds))
        self._now = now or datetime.now
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._tasks: dict[int, _Task] = {}
        self._waiting: dict[int, _Task] = {}
        self._ready: deque[int] = deque()
        self._run_task: dict[int, _Task] = {}
        self._dep_tasks: dict[int, int] = {}
        self._next_id = 1

    # ------------------------------------------------------------- 生命周期

    def start(self) -> None:
        """启动守护线程；启动前先处理错过的调度。"""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self.tick_once(startup=True)
            self._thread = threading.Thread(
                target=self._loop, name="autobranch-scheduler", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self._tick_seconds)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self.tick_once()
            except Exception:  # noqa: BLE001 - 单次 tick 失败不杀死调度线程
                logger.exception("调度 tick 异常")

    # ------------------------------------------------------------- 主循环入口

    def tick_once(
        self, now: datetime | None = None, *, startup: bool = False
    ) -> None:
        """执行一次检查（测试直接调用；后台线程按 tick_seconds 调用）。"""
        current = now or self._now()
        with self._lock:
            self._check_due_rules(current, startup=startup)
            self._advance_waiting(current)
            self._dispatch_ready(current)

    def on_run_complete(self, run_id: int, status: str) -> None:
        """RunService 终态回调：更新目标/依赖状态并继续调度。"""
        with self._lock:
            try:
                self._handle_completion(run_id, status)
            except Exception:  # noqa: BLE001 - 回调异常不污染执行线程
                logger.exception("调度完成回调异常 (run_id=%s)", run_id)
        self._wake.set()

    # ------------------------------------------------------------- 规则检查

    def _check_due_rules(self, now: datetime, *, startup: bool) -> None:
        db = session_factory()()
        try:
            rules = db.scalars(
                select(ScheduleRule).where(ScheduleRule.enabled.is_(True))
            ).all()
            for rule in rules:
                last = rule.last_run_at
                if last is None:
                    due = True
                else:
                    next_run = calculate_next_run(rule, last)
                    due = next_run is not None and now >= next_run
                if not due:
                    continue

                if startup and last is not None and rule.on_missed == "skip":
                    rule.last_run_at = now
                    rule.last_status = "skipped"
                    rule.last_error = "错过调度周期，已按策略跳过"
                    db.commit()
                    continue

                # 先落 last_run_at，避免异常时同一周期重复触发。
                rule.last_run_at = now
                rule.last_status = "pending"
                rule.last_error = None
                db.commit()
                self._enqueue(self._task_from_rule(rule, now))
        finally:
            db.close()

    def _task_from_rule(self, rule: ScheduleRule, now: datetime) -> _Task:
        return _Task(
            id=self._new_id(),
            kind="schedule",
            rule_id=rule.id,
            target_tree_id=rule.target_tree_id,
            dependencies=list(rule.dependencies or []),
            inputs=dict(rule.inputs or {}),
            source="schedule",
            created_at=now,
            on_failure=rule.on_failure,
            max_retries=rule.max_retries,
            retry_interval=rule.retry_interval,
        )

    # ------------------------------------------------------------- 依赖推进

    def _advance_waiting(self, now: datetime) -> None:
        db = session_factory()()
        try:
            work = list(self._waiting)
            seen: set[int] = set()
            while work:
                task_id = work.pop(0)
                if task_id in seen:
                    continue
                seen.add(task_id)
                task = self._waiting.get(task_id)
                if task is None:
                    continue
                if task.next_attempt_at is not None and task.next_attempt_at > now:
                    continue
                for dep in task.dependencies:
                    if dep in task.satisfied:
                        continue
                    status = self._latest_run_status(db, dep)
                    if status == "success":
                        task.satisfied.add(dep)
                    elif status in ("pending", "running"):
                        continue
                    else:
                        new_task = self._ensure_dependency_task(db, dep, task, now)
                        if new_task is not None:
                            work.append(new_task.id)
                if all(dep in task.satisfied for dep in task.dependencies):
                    self._waiting.pop(task.id, None)
                    if task.id not in self._ready:
                        self._ready.append(task.id)
        finally:
            db.close()

    def _ensure_dependency_task(
        self, db: Session, dep_tree_id: int, parent: _Task, now: datetime
    ) -> _Task | None:
        if dep_tree_id in self._dep_tasks:
            return None
        if self._latest_run_status(db, dep_tree_id) in ("pending", "running"):
            return None

        rules = db.scalars(
            select(ScheduleRule).where(ScheduleRule.target_tree_id == dep_tree_id)
        ).all()
        deps: set[int] = set()
        inputs: dict = {}
        for rule in rules:
            deps.update(int(item) for item in (rule.dependencies or []))
            if not inputs:
                inputs = dict(rule.inputs or {})
        deps.discard(dep_tree_id)

        task = _Task(
            id=self._new_id(),
            kind="dependency",
            rule_id=parent.rule_id,
            target_tree_id=dep_tree_id,
            dependencies=sorted(deps),
            inputs=inputs,
            source="dependency",
            created_at=now,
            # 依赖任务本身不重试；失败交给等待它的父任务按父规则重试。
            on_failure="next_schedule",
            max_retries=0,
            retry_interval=parent.retry_interval,
        )
        self._dep_tasks[dep_tree_id] = task.id
        self._tasks[task.id] = task
        self._waiting[task.id] = task
        return task

    @staticmethod
    def _latest_run_status(db: Session, tree_id: int) -> str | None:
        run = db.scalar(
            select(Run)
            .where(Run.tree_id == tree_id)
            .order_by(Run.created_at.desc(), Run.id.desc())
            .limit(1)
        )
        return run.status if run is not None else None

    # ------------------------------------------------------------- 提交执行

    def _dispatch_ready(self, now: datetime) -> None:
        while self._ready:
            task_id = self._ready.popleft()
            task = self._tasks.get(task_id)
            if task is None:
                continue

            db = session_factory()()
            try:
                tree = db.get(Tree, task.target_tree_id)
                if tree is None:
                    self._fail_task(task, "目标行为树不存在", now, retryable=False)
                    continue
                if tree.status != "published":
                    self._fail_task(
                        task, "目标行为树处于草稿状态，等待保存为正式版", now, retryable=False
                    )
                    continue
                try:
                    validate_run_inputs(tree.content, task.inputs)
                except AppError as exc:
                    self._fail_task(task, str(exc.detail), now, retryable=False)
                    continue
                try:
                    run = self._run_service.start(
                        db,
                        tree.id,
                        inputs=task.inputs,
                        source=task.source,
                        schedule_id=task.rule_id,
                    )
                except Exception as exc:  # noqa: BLE001 - 单任务失败不影响其他任务
                    logger.exception("调度提交执行失败 (task=%s)", task.id)
                    self._fail_task(task, f"提交执行失败: {exc}", now, retryable=False)
                    continue

                task.run_id = run.id
                self._run_task[run.id] = task
                if task.kind == "schedule" and task.rule_id is not None:
                    rule = db.get(ScheduleRule, task.rule_id)
                    if rule is not None:
                        rule.last_status = "running"
                        rule.last_run_id = run.id
                        rule.last_error = None
                        db.commit()
            finally:
                db.close()

    # ------------------------------------------------------------- 完成回调

    def _handle_completion(self, run_id: int, status: str) -> None:
        task = self._run_task.pop(run_id, None)
        db = session_factory()()
        try:
            run = db.get(Run, run_id)
            tree_id = run.tree_id if run is not None else None
            reason = (run.failure_reason if run is not None else None) or "执行失败"
        finally:
            db.close()

        if task is not None:
            self._tasks.pop(task.id, None)
            if task.kind == "dependency":
                self._dep_tasks.pop(task.target_tree_id, None)

        now = self._now()
        if status == "success":
            if task is not None and task.kind == "schedule" and task.rule_id is not None:
                self._update_rule(task.rule_id, status="success", error=None)
            if tree_id is not None:
                for waiting in self._waiting.values():
                    if tree_id in waiting.dependencies:
                        waiting.satisfied.add(tree_id)
            self._advance_waiting(now)
            self._dispatch_ready(now)
            return

        if task is not None:
            if task.kind == "dependency":
                self._on_dependency_failure(task.target_tree_id, reason, now)
            else:
                self._retry_or_fail(task, reason, now, retryable=True)
        elif tree_id is not None:
            # 手动/其他来源执行失败，也会影响正在等待该树的任务。
            self._on_dependency_failure(tree_id, reason, now)

        self._advance_waiting(now)
        self._dispatch_ready(now)

    # ------------------------------------------------------------- 失败/重试

    def _fail_task(
        self, task: _Task, reason: str, now: datetime, *, retryable: bool
    ) -> None:
        self._retry_or_fail(task, reason, now, retryable=retryable)

    def _retry_or_fail(
        self, task: _Task, reason: str, now: datetime, *, retryable: bool
    ) -> None:
        self._tasks.pop(task.id, None)
        self._waiting.pop(task.id, None)
        if task.kind == "dependency":
            self._dep_tasks.pop(task.target_tree_id, None)

        if (
            retryable
            and task.kind == "schedule"
            and task.on_failure == "immediate"
            and task.retry_count < task.max_retries
        ):
            task.retry_count += 1
            task.satisfied.clear()
            task.run_id = None
            task.next_attempt_at = now + timedelta(seconds=max(1, task.retry_interval))
            self._tasks[task.id] = task
            self._waiting[task.id] = task
            if task.rule_id is not None:
                self._update_rule(task.rule_id, status="retrying", error=reason)
            return

        if task.kind == "schedule":
            if task.rule_id is not None:
                self._update_rule(task.rule_id, status="failure", error=reason)
            return

        if task.kind == "dependency":
            self._on_dependency_failure(task.target_tree_id, reason, now)

    def _on_dependency_failure(self, tree_id: int, reason: str, now: datetime) -> None:
        for waiting in list(self._waiting.values()):
            if tree_id in waiting.dependencies and tree_id not in waiting.satisfied:
                self._retry_or_fail(
                    waiting,
                    f"前置依赖树 #{tree_id} 执行失败: {reason}",
                    now,
                    retryable=True,
                )

    def _update_rule(
        self, rule_id: int, *, status: str, error: str | None = None
    ) -> None:
        db = session_factory()()
        try:
            rule = db.get(ScheduleRule, rule_id)
            if rule is None:
                return
            rule.last_status = status
            rule.last_error = error
            db.commit()
        finally:
            db.close()

    # ------------------------------------------------------------- 手动立即执行

    def trigger_now(self, rule_id: int) -> int:
        """立即执行调度目标（不检查前置依赖，不改变 last_run_at）。"""
        with self._lock:
            db = session_factory()()
            try:
                rule = db.get(ScheduleRule, rule_id)
                if rule is None:
                    raise AppError(404, f"调度规则不存在 (id={rule_id})")
                tree = db.get(Tree, rule.target_tree_id)
                if tree is None:
                    raise AppError(404, "目标行为树不存在")
                if tree.status != "published":
                    raise AppError(409, "目标行为树处于草稿状态，请先保存为正式版")
                try:
                    validate_run_inputs(tree.content, rule.inputs or {})
                except AppError:
                    raise
                run = self._run_service.start(
                    db,
                    tree.id,
                    inputs=dict(rule.inputs or {}),
                    source="schedule",
                    schedule_id=rule.id,
                )
                rule.last_status = "running"
                rule.last_run_id = run.id
                rule.last_error = None
                db.commit()

                task = _Task(
                    id=self._new_id(),
                    kind="schedule",
                    rule_id=rule.id,
                    target_tree_id=tree.id,
                    dependencies=[],
                    inputs=dict(rule.inputs or {}),
                    source="schedule",
                    created_at=self._now(),
                    # 手动立即执行不进入自动重试循环。
                    on_failure="next_schedule",
                    max_retries=0,
                    retry_interval=rule.retry_interval,
                    run_id=run.id,
                )
                self._tasks[task.id] = task
                self._run_task[run.id] = task
                return run.id
            finally:
                db.close()

    # ------------------------------------------------------------- 工具

    def _new_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    def _enqueue(self, task: _Task) -> None:
        self._tasks[task.id] = task
        self._waiting[task.id] = task

    @property
    def waiting_count(self) -> int:
        return len(self._waiting)

    @property
    def ready_count(self) -> int:
        return len(self._ready)

    @property
    def active_run_count(self) -> int:
        return len(self._run_task)


__all__ = ["SchedulerEngine"]
