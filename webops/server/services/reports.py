"""报告/截图文件服务（database-rules §6、api-conventions §7）。

- 文件本体落盘 ``<report_root>/<run_id>/``（引擎 M8 直接产出），库中只存
  相对路径；本服务负责相对路径解析（白名单防目录穿越）、读取与清理。
- ``GET /api/reports/{path}`` 经 ``resolve`` 做白名单校验后提供。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from webops.server.errors import AppError

#: 报告根内不允许解析出的相对路径文件名（防御性：只允许白名单内）。
_REPORT_FILENAMES = ("exec_report.md", "trace_report.md")


class ReportService:
    """报告/截图文件服务（报告根经构造注入，测试可指向临时目录）。"""

    def __init__(self, report_root: Path) -> None:
        self.report_root = report_root.resolve()

    def ensure_root(self) -> Path:
        self.report_root.mkdir(parents=True, exist_ok=True)
        return self.report_root

    def resolve(self, rel_path: str) -> Path:
        """白名单解析：逃逸报告根返回 400（api-conventions §7）。"""
        if not rel_path or rel_path.strip() in ("", "/"):
            raise AppError(400, "无效的报告路径")
        target = (self.report_root / rel_path).resolve()
        if not target.is_relative_to(self.report_root):
            raise AppError(400, "报告路径越界：禁止目录穿越")
        return target

    def file_path(self, run_id: int, filename: str) -> Path:
        """``<report_root>/<run_id>/<filename>`` 白名单化路径。"""
        if filename not in _REPORT_FILENAMES:
            raise AppError(400, f"不允许的报告文件名: {filename}")
        return self.resolve(f"{run_id}/{filename}")

    def read_text(self, run_id: int, filename: str) -> str:
        path = self.file_path(run_id, filename)
        if not path.is_file():
            raise AppError(404, f"报告文件不存在: {run_id}/{filename}")
        return path.read_text(encoding="utf-8")

    def rel_path(self, abs_path: str | Path) -> str:
        """把引擎产出的绝对路径转为相对报告根的路径（库中存储用）。"""
        abs_path = Path(abs_path)
        try:
            rel = abs_path.relative_to(self.report_root)
        except ValueError:
            rel = Path(abs_path.name)
        return rel.as_posix()

    def cleanup_run(self, run_id: int) -> None:
        """删除 run 的报告目录（删除行为树/执行记录时清理文件，设计 Risk）。"""
        target = (self.report_root / str(run_id)).resolve()
        if target.is_relative_to(self.report_root):
            shutil.rmtree(target, ignore_errors=True)


__all__ = ["ReportService"]
