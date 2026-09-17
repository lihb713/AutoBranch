"""报告记录器（M8）：节点报告记录、截图、两份报告生成与执行状态维护。

设计要点（design.md）：
- 被动记录器（决策 1）：由 M7 在节点退出前调用 ``record_node``、在叶子返回前
  调用 ``capture_screenshot``，M8 不主动 hook 遍历器。
- 单数据源（决策 3）：``ExecState.completed`` 即已记录的节点报告，
  ``finalize`` 从全部节点报告派生两份报告，轮询与最终报告始终一致。
- 截图即落盘（决策 4）：``capture_screenshot`` 时截图写入存储目录，
  ``NodeReport.screenshot_path`` 只引用路径。
- 存储按 run_id 归组（决策 5）：``<report_dir>/<run_id>/`` 下存放截图与
  两份报告文件。
- 截图能力（M1 ``PageHandle.screenshot``）经 ``screenshotter`` 回调注入，
  保持 M8 对 M1 的单方向、可 mock 依赖。
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable

from autobranch.browser.models import OpResult, PageRef
from autobranch.reporting.models import (
    ExecReport,
    ExecState,
    NodeInfo,
    NodeReport,
    ReportBundle,
    TraceReport,
)
from autobranch.reporting.render import render_exec_report, render_trace_report

logger = logging.getLogger(__name__)

#: M1 截图回调：按 (page_ref, 目标路径) 调用 M1 截图能力并返回 ``OpResult``。
Screenshotter = Callable[[PageRef, str], OpResult]

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]")
_SLUG_RE = re.compile(r"[^A-Za-z0-9\u4e00-\u9fff._-]+")


def sanitize_run_id(run_id: str) -> str:
    """run_id 清洗为安全目录名（保留字母/数字/点/下划线/连字符）。"""
    cleaned = _SANITIZE_RE.sub("_", run_id)
    return cleaned or "run"


def slugify(text: str) -> str:
    """把描述片段转为安全文件名片段（供截图命名，决策 5）。"""
    slug = _SLUG_RE.sub("_", text).strip("._")
    return slug[:40] or "node"


class Reporter:
    """被动报告记录器（M8 spec §5.1），供 M7 调用。

    :param run_id: 运行标识（存储目录按其清洗结果命名）。
    :param report_dir: 报告/截图持久化根目录。
    :param screenshotter: 包装 M1 ``PageHandle.screenshot`` 的回调
      ``(page_ref, path) -> OpResult``；不注入则截图被跳过。
    :param total_nodes: 树中节点总数（执行前已知），供 ``progress`` 计算。
    """

    def __init__(
        self,
        run_id: str,
        report_dir: str,
        screenshotter: Screenshotter | None = None,
        total_nodes: int | None = None,
    ) -> None:
        self._raw_run_id = run_id
        self._run_id = sanitize_run_id(run_id)
        self._report_dir = report_dir
        self._screenshotter = screenshotter
        self._state = ExecState(run_id=run_id, total_nodes=total_nodes)
        self._run_root = os.path.join(report_dir, self._run_id)
        self._screenshot_index = 0
        os.makedirs(self._run_root, exist_ok=True)

    @property
    def run_id(self) -> str:
        """原始运行标识。"""
        return self._raw_run_id

    @property
    def run_root(self) -> str:
        """该运行（run_id）的持久化存储目录。"""
        return self._run_root

    # ------------------------------------------------------------------ 记录

    def start_node(self, node_info: NodeInfo) -> None:
        """标记当前开始执行的节点，更新 ``ExecState.current_node``（§12.4）。

        M7 在节点进入执行前调用；节点完成调用 ``record_node`` 后清空。
        """
        self._state.current_node = node_info

    def record_node(self, node_report: NodeReport) -> None:
        """记录一条节点报告（节点退出前，M8 spec §5.1）。

        追加到已完成报告列表（顺序即记录顺序）；该节点执行完毕，
        ``current_node`` 清空，等待下一个 ``start_node``。
        """
        self._state.completed.append(node_report)
        self._state.current_node = None

    # ------------------------------------------------------------------ 截图

    def capture_screenshot(self, page_ref: PageRef, desc: str | None = None) -> str:
        """叶子返回前截图当前页面状态（契约 §5.8.3），返回持久化路径。

        经注入的 ``screenshotter``（包装 M1）把截图写入本运行存储目录；
        截图失败（异常或 ``ok=False``）记录日志并返回空串，不中断执行与记录。
        """
        if self._screenshotter is None:
            logger.warning("未注入截图能力，跳过截图（page_ref=%s）", page_ref.id)
            return ""
        self._screenshot_index += 1
        filename = f"{self._screenshot_index:03d}_{slugify(desc) if desc else 'shot'}.png"
        target = os.path.join(self._run_root, filename)
        try:
            result = self._screenshotter(page_ref, target)
        except Exception as exc:  # 截图异常按失败处理，不影响节点记录（任务 2.2）
            logger.warning("截图失败（page_ref=%s）: %s", page_ref.id, exc)
            return ""
        if not result.ok:
            logger.warning("截图失败（page_ref=%s）: %s", page_ref.id, result.error)
            return ""
        detail = result.detail if isinstance(result.detail, dict) else None
        path = detail.get("path") if detail else None
        return path or target

    # ------------------------------------------------------------------ 状态

    def exec_state(self) -> ExecState:
        """执行状态查询快照（契约 §12.4）：返回副本，查询不改变执行本身。

        ``completed`` 返回副本列表，调用方修改不影响记录器内部状态。
        """
        return ExecState(
            run_id=self._raw_run_id,
            current_node=self._state.current_node,
            completed=list(self._state.completed),
            finished=self._state.finished,
            total_nodes=self._state.total_nodes,
        )

    # ------------------------------------------------------------------ finalize

    def finalize(self) -> ReportBundle:
        """流程结束：生成并落盘两份报告、标记执行完毕（决策 3 单数据源）。

        执行报告（报告①，含截图）与回溯报告（报告②，含 LLM 推理）均由全部
        已记录节点报告派生；文件写入 ``<report_dir>/<run_id>/``。
        """
        reports = list(self._state.completed)
        exec_text = render_exec_report(self._raw_run_id, reports)
        trace_text = render_trace_report(self._raw_run_id, reports)
        exec_path = os.path.join(self._run_root, "exec_report.md")
        trace_path = os.path.join(self._run_root, "trace_report.md")
        self._write(exec_path, exec_text)
        self._write(trace_path, trace_text)
        self._state.finished = True
        return ReportBundle(
            exec_report=ExecReport(run_id=self._raw_run_id, path=exec_path, text=exec_text),
            trace_report=TraceReport(run_id=self._raw_run_id, path=trace_path, text=trace_text),
        )

    def _write(self, path: str, text: str) -> None:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
