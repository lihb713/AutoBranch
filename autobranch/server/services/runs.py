"""执行服务：触发、快照执行、FIFO 队列调度、状态轮询与报告获取（Change A）。

执行流程：
  ① ``POST /run``：执行前校验（M2）→ 冻结快照（内容/树名/执行结构指纹/入参）
     → 建 ``Run``（pending=排队中）→ 触发 ``_drain()``；
  ② ``_drain()`` 队列调度：并发未满取最早 pending，先置 running 占位再提交到
     ``ThreadPoolExecutor``；``execute_async`` 从**快照**执行（不读实时树），
     落终态（status/failure_reason/outputs/report_path）；异常统一写 failure；
     执行结束再触发 ``_drain()`` 调度下一个；
  ③ 轮询 ``GET /state``：进行中读引擎 ``get_exec_state()`` 内存快照，结束读
     引擎终态快照（内存）或 ``runs`` 表持久化终态（进程重启后）。
  ④ 报告 ``GET /report``、``/trace``：结束后读 M8 落盘报告。

并发控制：全局并发上限（``max_concurrent_runs``，默认 3）+ FIFO 队列；
同树/异树均可并发，超上限进排队（不再有同树 409 去重）。
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from autobranch.config import AutoBranchConfig
from autobranch.parser.snapshot import compute_tree_content_hash
from autobranch.reporting.models import ActionCall, ExecState, NodeInfo, NodeReport
from autobranch.schema.models import PageRef
from autobranch.server.db import session_factory
from autobranch.server.errors import AppError, CheckValidationError
from autobranch.server.models import Run, Tree
from autobranch.server.schemas.run import (
    ActionCallOut,
    ExecStateOut,
    NodeInfoOut,
    NodeReportOut,
)
from autobranch.server.services.engine import EngineService
from autobranch.server.services.reports import ReportService
from autobranch.server.services.validation import validate_document

logger = logging.getLogger(__name__)

#: 进行中状态（报告不可用判定用）。
_ACTIVE_STATUSES = ("pending", "running")

#: 出参对象 str 化展示上限（防超长入库/展示）。
_OUTPUT_STR_LIMIT = 2000


def _json_safe_output(value: object) -> object:
    """出参 JSON 安全序列化：标量原样（长文本截断）；PageRef→{page_id,url}；对象→str。"""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= _OUTPUT_STR_LIMIT else value[:_OUTPUT_STR_LIMIT] + "…"
    if isinstance(value, PageRef):
        return {"page_id": value.page_id, "url": value.url}
    text = str(value)
    if len(text) > _OUTPUT_STR_LIMIT:
        text = text[:_OUTPUT_STR_LIMIT] + "…"
    return text


def serialize_outputs(outputs: dict[str, object]) -> dict[str, object]:
    """把引擎出参转为 JSON 安全可入库的表示（展示用途，不承诺完整还原对象）。"""
    return {name: _json_safe_output(value) for name, value in outputs.items()}


def _issues_summary(detail: list) -> str:
    if not detail:
        return "校验失败"
    first = detail[0]
    return f"{first.get('code', '')}: {first.get('message', '')}"


def validate_run_inputs(content: str, inputs: dict | None) -> None:
    """校验执行入参（Change A 任务 4.1）。

    - 声明含不可由文本构造的类型（``TypeSpec.cast is None``，如 page_ref/object）
      → 422（仅支持 ref 调用）。
    - 提供的入参必须是声明内的，且可按声明类型 ``coerce``。
    """
    from autobranch.parser.yamlio import normalize_document
    from autobranch.schema import TYPE_REGISTRY, coerce
    from autobranch.schema.errors import SchemaTypeError

    declared_raw = (normalize_document(content) or {}).get("inputs") or {}
    if isinstance(declared_raw, dict):
        declared = {str(k): str(v) for k, v in declared_raw.items()}
    else:
        declared = {}
    for name, type_name in declared.items():
        spec = TYPE_REGISTRY.get(type_name)
        if spec is None or spec.cast is None:
            raise AppError(422, f"入参 {name} 类型 {type_name} 不可由文本构造，该树仅支持 ref 调用")
    for name, value in (inputs or {}).items():
        type_name = declared.get(name)
        if type_name is None:
            raise AppError(422, f"未声明的入参: {name}（声明: {', '.join(declared) or '无'}）")
        spec = TYPE_REGISTRY.get(type_name)
        if spec is not None and spec.cast is not None:
            try:
                coerce(type_name, value)
            except SchemaTypeError as exc:
                raise AppError(422, f"入参 {name} 类型校验失败: {exc}") from None


class RunService:
    """执行服务（引擎经构造注入，测试可替换 mock；含 FIFO 队列调度）。"""

    def __init__(
        self,
        engine_service: EngineService,
        report_root: Path,
        config: AutoBranchConfig,
        registry: object | None = None,
    ) -> None:
        self._engine = engine_service
        self._report_root = report_root
        self._registry = registry
        self._config = config
        self._reports = ReportService(report_root)
        self._max_concurrent = max(1, config.max_concurrent_runs)
        self._executor: ThreadPoolExecutor | None = None
        self._sched_lock = threading.Lock()

    @property
    def max_concurrent_runs(self) -> int:
        """当前并发上限（执行列表页展示用）。"""
        return self._max_concurrent

    def shutdown(self) -> None:
        """释放线程池（应用关闭时调用；不等待在跑任务）。"""
        with self._sched_lock:
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._executor = None

    # ------------------------------------------------------------- 触发

    def start(self, db: Session, tree_id: int, *, inputs: dict | None = None) -> Run:
        """冻结快照（内容/树名/指纹/入参）→ 建 pending Run → 触发队列调度。

        执行前校验已由路由层完成（422 拒绝）；此处读实时树内容冻结为快照，
        执行与重试一律基于快照，不读实时树内容。
        """
        tree = db.get(Tree, tree_id)
        if tree is None:
            raise AppError(404, f"行为树不存在 (id={tree_id})")
        content = tree.content
        run = Run(
            tree_id=tree_id,
            status="pending",
            content_snapshot=content,
            tree_name_snapshot=tree.name,
            tree_content_hash=compute_tree_content_hash(content),
            inputs=dict(inputs or {}),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        self._drain()
        return run

    def retry(self, db: Session, run_id: int) -> Run:
        """按快照重试：复制原实例的快照 + 入参新建 Run（跑当时的内容，非最新树）。"""
        source = self._get_run(db, run_id)
        run = Run(
            tree_id=source.tree_id,
            status="pending",
            content_snapshot=source.content_snapshot,
            tree_name_snapshot=source.tree_name_snapshot,
            tree_content_hash=source.tree_content_hash,
            inputs=dict(source.inputs or {}),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        self._drain()
        return run

    def delete(self, db: Session, run_id: int) -> None:
        """删除执行实例：删记录并清理其报告目录。"""
        run = self._get_run(db, run_id)
        db.delete(run)
        db.commit()
        self._reports.cleanup_run(run_id)

    # ------------------------------------------------------------- 队列调度

    def _ensure_executor(self) -> ThreadPoolExecutor:
        # 调用方须持有 self._sched_lock（_drain / shutdown），此处不再重复加锁。
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_concurrent, thread_name_prefix="run"
            )
        return self._executor

    def _drain(self) -> None:
        """调度队列：并发未满时取最早 pending，置 running 占位后提交执行。

        在 ``start`` / 每次执行结束路径调用；进程内锁防并发双调度。
        """
        with self._sched_lock:
            executor = self._ensure_executor()
            db = session_factory()()
            try:
                while True:
                    running = db.scalar(
                        select(func.count()).select_from(Run).where(Run.status == "running")
                    )
                    if running >= self._max_concurrent:
                        break
                    pending = db.scalar(
                        select(Run)
                        .where(Run.status == "pending")
                        .order_by(Run.created_at, Run.id)
                        .limit(1)
                    )
                    if pending is None:
                        break
                    pending.status = "running"
                    db.commit()
                    run_id = pending.id
                    executor.submit(self._run_task, run_id)
            finally:
                db.close()

    def _run_task(self, run_id: int) -> None:
        """执行任务（executor 线程）：跑引擎 → 落终态 → 再调度下一个。"""
        try:
            self.execute_async(run_id)
        except Exception:
            logger.exception("执行任务未预期异常 (run_id=%s)", run_id)
        finally:
            self._drain()

    # ------------------------------------------------------------- 后台执行

    def execute_async(self, run_id: int) -> None:
        """从实例**快照**执行（不读实时树），落终态（独立新会话，异常捕获不中断）。

        状态已由 ``_drain`` 置 running；树被删除时仍可基于快照执行（自包含）。
        """
        db = session_factory()()
        try:
            run = db.get(Run, run_id)
            if run is None:
                return
            tree_id = run.tree_id
            content = run.content_snapshot
            tree_name = run.tree_name_snapshot
            try:
                from autobranch.server.services.doclib import DbResolver

                parsed = validate_document(
                    content, tree_name, resolver=DbResolver(db), registry=self._registry
                )
            except CheckValidationError as exc:
                self._set_failed(db, run_id, f"执行前校验失败: {_issues_summary(exc.detail)}")
                return
            result = self._engine.run(
                tree_id,
                content,
                run_id,
                doc_id=parsed.tree.name,
                run_inputs=dict(run.inputs or {}),
            )
            self._finalize(db, run_id, result)
        except Exception as exc:
            logger.exception("后台执行未预期异常 (run_id=%s)", run_id)
            self._set_failed(db, run_id, f"执行异常: {exc}")
        finally:
            db.close()

    def _finalize(self, db: Session, run_id: int, result) -> None:
        status = "success" if result.status == "success" else "failure"
        report_path = None
        if getattr(result, "exec_report", None) is not None and result.exec_report.path:
            report_path = self._reports.rel_path(result.exec_report.path)
        run = db.get(Run, run_id)
        run.status = status
        run.failure_reason = result.failure_reason if status == "failure" else None
        run.outputs = (
            serialize_outputs(result.outputs) if getattr(result, "outputs", None) else None
        )
        run.report_path = report_path
        db.commit()

    def _set_failed(self, db: Session, run_id: int, reason: str) -> None:
        try:
            run = db.get(Run, run_id)
            if run is None:
                return
            run.status = "failure"
            run.failure_reason = reason
            db.commit()
        except Exception:
            logger.exception("写入失败状态异常 (run_id=%s)", run_id)

    # ------------------------------------------------------------- 列表

    def _run_item(self, run: Run) -> dict:
        duration = None
        if run.status in ("success", "failure") and run.created_at and run.updated_at:
            duration = round((run.updated_at - run.created_at).total_seconds(), 3)
        progress = None
        if run.status in _ACTIVE_STATUSES:
            state = self._engine.get_exec_state(run.id)
            if state is not None:
                progress = round(state.progress, 6)
        return {
            "id": run.id,
            "tree_id": run.tree_id,
            "tree_name": run.tree_name_snapshot,
            "status": run.status,
            "inputs": run.inputs or {},
            "outputs": run.outputs,
            "tree_content_hash": run.tree_content_hash,
            "failure_reason": run.failure_reason,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "duration": duration,
            "progress": progress,
        }

    def list_runs(self, db: Session) -> list[dict]:
        """执行实例列表（created_at 倒序）：含耗时与进行中实例的进度。"""
        runs = db.scalars(select(Run).order_by(Run.created_at.desc(), Run.id.desc())).all()
        return [self._run_item(run) for run in runs]

    def get_detail(self, db: Session, run_id: int) -> dict:
        """执行实例详情（含快照内容，供"查看快照"）。"""
        run = self._get_run(db, run_id)
        item = self._run_item(run)
        item["content_snapshot"] = run.content_snapshot
        return item

    # ------------------------------------------------------------- 状态轮询

    def get_state(self, db: Session, run_id: int) -> ExecStateOut:
        """轮询执行状态（设计 D4）：引擎内存快照优先，缺省回落持久化终态。"""
        run = self._get_run(db, run_id)
        state = self._engine.get_exec_state(run_id)
        if state is not None:
            failure_reason = run.failure_reason if run.status == "failure" else None
            return self._state_out(state, failure_reason)
        if run.status in _ACTIVE_STATUSES:
            return ExecStateOut(run_id=str(run_id), progress=0.0, finished=False)
        return ExecStateOut(
            run_id=str(run_id),
            progress=1.0,
            finished=True,
            failure_reason=run.failure_reason,
        )

    @staticmethod
    def _state_out(state: ExecState, failure_reason: str | None) -> ExecStateOut:
        return ExecStateOut(
            run_id=state.run_id or "run",
            progress=round(state.progress, 6),
            current_node=_node_info_out(state.current_node),
            completed=[_node_report_out(nr) for nr in state.completed],
            finished=state.finished,
            failure_reason=failure_reason,
            variables=list(state.variables),
        )

    # ------------------------------------------------------------- 报告获取

    def get_report(self, db: Session, run_id: int) -> dict | str:
        """执行报告：进行中返回状态标识，结束返回 M8 落盘报告文本。"""
        run = self._get_run(db, run_id)
        if run.status in _ACTIVE_STATUSES:
            return {"run_id": run_id, "status": "running", "message": "执行尚未完成"}
        return self._reports.read_text(run_id, "exec_report.md")

    def get_trace(self, db: Session, run_id: int) -> dict | str:
        """回溯报告：进行中返回状态标识，结束返回 M8 落盘回溯报告文本。"""
        run = self._get_run(db, run_id)
        if run.status in _ACTIVE_STATUSES:
            return {"run_id": run_id, "status": "running", "message": "执行尚未完成"}
        return self._reports.read_text(run_id, "trace_report.md")

    # ------------------------------------------------------------- 内部

    def _get_run(self, db: Session, run_id: int) -> Run:
        run = db.get(Run, run_id)
        if run is None:
            raise AppError(404, f"执行记录不存在 (run_id={run_id})")
        return run

    @staticmethod
    def mark_interrupted() -> int:
        """启动恢复（设计 Risk/任务 6.2）：进行中记录置 failure（interrupted）。"""
        db = session_factory()()
        try:
            rows = (
                db.query(Run)
                .filter(Run.status.in_(_ACTIVE_STATUSES))
                .update({Run.status: "failure", Run.failure_reason: "interrupted"})
            )
            db.commit()
            return int(rows or 0)
        finally:
            db.close()


def _node_info_out(info: NodeInfo | None) -> NodeInfoOut | None:
    if info is None:
        return None
    return NodeInfoOut(node_type=info.node_type, node_desc=info.node_desc)


def _node_report_out(report: NodeReport) -> NodeReportOut:
    return NodeReportOut(
        node_type=report.node_type,
        node_desc=report.node_desc,
        result=report.result,
        timestamp=report.timestamp,
        action_call=_action_call_out(report.action_call),
        condition_result=report.condition_result,
        page_url=report.page_url,
        screenshot_path=report.screenshot_path,
    )


def _action_call_out(call: ActionCall | None) -> ActionCallOut | None:
    if call is None:
        return None
    return ActionCallOut(
        function=call.function,
        success=call.success,
        arguments=call.arguments,
        error=call.error,
    )


__all__ = ["RunService"]
