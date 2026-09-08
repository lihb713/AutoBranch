"""执行服务：触发、后台执行、状态轮询与报告获取（设计 D3/D4、契约 §12.4）。

执行流程（§12.4）：
  ① ``POST /run``：执行前校验（M2）→ 建 ``Run``（pending）返回 run_id（202）；
  ② ``execute_async`` 后台任务：置 running → 调 ``EngineService.run``（内嵌
     M7）→ 落终态（status/failure_reason/report_path）；异常统一写 failure；
  ③ 轮询 ``GET /state``：进行中读引擎 ``get_exec_state()`` 内存快照，结束读
     引擎终态快照（内存）或 ``runs`` 表持久化终态（进程重启后，D4）。
  ④ 报告 ``GET /report``、``/trace``：结束后读 M8 落盘报告。

并发控制（D8）：同一 tree 存在 pending/running 的 run 时拒绝新触发（409）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from webops.config import WebOpsConfig
from webops.reporting.models import ActionCall, ExecState, NodeInfo, NodeReport
from webops.server.db import session_factory
from webops.server.errors import AppError, CheckValidationError
from webops.server.models import Run, Tree
from webops.server.schemas.run import (
    ActionCallOut,
    ExecStateOut,
    NodeInfoOut,
    NodeReportOut,
)
from webops.server.services.engine import EngineService
from webops.server.services.reports import ReportService
from webops.server.services.validation import validate_document

logger = logging.getLogger(__name__)

#: 进行中状态（并发去重 / 报告不可用判定用）。
_ACTIVE_STATUSES = ("pending", "running")


def _issues_summary(detail: list) -> str:
    if not detail:
        return "校验失败"
    first = detail[0]
    return f"{first.get('code', '')}: {first.get('message', '')}"


class RunService:
    """执行服务（引擎经构造注入，测试可替换 mock）。"""

    def __init__(
        self,
        engine_service: EngineService,
        report_root: Path,
        config: WebOpsConfig,
    ) -> None:
        self._engine = engine_service
        self._report_root = report_root
        self._config = config
        self._reports = ReportService(report_root)

    # ------------------------------------------------------------- 触发

    def start(self, db: Session, tree_id: int) -> Run:
        """执行前校验（已由路由层完成 422 拒绝）→ 并发去重 → 建 pending Run。"""
        active = db.scalar(
            select(Run).where(Run.tree_id == tree_id, Run.status.in_(_ACTIVE_STATUSES))
        )
        if active is not None:
            raise AppError(409, f"该行为树已有进行中的执行 (run_id={active.id})")
        run = Run(tree_id=tree_id, status="pending")
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    # ------------------------------------------------------------- 后台执行

    def execute_async(self, run_id: int, tree_id: int) -> None:
        """后台任务：运行内嵌引擎并落终态（独立新会话，异常捕获不中断任务）。"""
        db = session_factory()()
        try:
            self._set_status(db, run_id, "running")
            tree = db.get(Tree, tree_id)
            if tree is None:
                self._set_failed(db, run_id, "行为树不存在")
                return
            try:
                parsed = validate_document(tree.content)
            except CheckValidationError as exc:
                self._set_failed(db, run_id, f"执行前校验失败: {_issues_summary(exc.detail)}")
                return
            result = self._engine.run(tree_id, tree.content, run_id, doc_id=parsed.tree.name)
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
        run.report_path = report_path
        db.commit()

    def _set_status(self, db: Session, run_id: int, status: str) -> None:
        run = db.get(Run, run_id)
        if run is None:
            return
        run.status = status
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
