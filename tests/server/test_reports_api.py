"""报告/截图存储与 HTTP 提供测试（任务 7.1/7.2/7.3）。

覆盖：报告文件落盘与相对路径入库、``GET /api/reports/{path}`` 白名单
（目录穿越 400 / 不存在 404 / 正常文件 200）、执行报告/回溯报告接口
（进行中返回状态标识，结束后返回报告内容）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from webops.server.models import Run
from webops.server.services.reports import ReportService

from .conftest import create_tree

# ------------------------------------------------------------- 报告服务（7.1）

def test_report_service_write_and_rel_path(tmp_path):
    service = ReportService(tmp_path / "reports")
    root = service.ensure_root()
    run_dir = root / "3"
    run_dir.mkdir()
    (run_dir / "exec_report.md").write_text("# 报告", encoding="utf-8")

    rel = service.rel_path(run_dir / "exec_report.md")
    assert rel == "3/exec_report.md"
    assert service.resolve(rel).is_file()
    assert service.read_text(3, "exec_report.md") == "# 报告"


def test_report_service_cleanup(tmp_path):
    service = ReportService(tmp_path / "reports")
    run_dir = service.ensure_root() / "5"
    run_dir.mkdir()
    (run_dir / "exec_report.md").write_text("x", encoding="utf-8")
    service.cleanup_run(5)
    assert not run_dir.exists()


def test_report_service_rel_path_outside_falls_back_to_name(tmp_path):
    service = ReportService(tmp_path / "reports")
    assert service.rel_path(Path("outside/exec_report.md")) == "exec_report.md"


# ------------------------------------------------------------- 文件提供（7.2）

def _write_report_file(settings, run_id, filename, content):
    target = settings.report_root / str(run_id) / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8"))
    return target


def test_report_file_served(client, settings):
    _write_report_file(settings, 1, "exec_report.md", "# 执行报告\nok")
    resp = client.get("/api/reports/1/exec_report.md")
    assert resp.status_code == 200
    assert resp.text == "# 执行报告\nok"
    assert resp.headers["content-type"].startswith("text/markdown")


def test_report_screenshot_served(client, settings):
    target = settings.report_root / "1" / "001_shot.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    resp = client.get("/api/reports/1/001_shot.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")


def test_report_file_missing_404(client, settings):
    resp = client.get("/api/reports/1/nope.md")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/api/reports/../webops.config.json",
        "/api/reports/%2e%2e/%2e%2e/webops.config.json",
        "/api/reports/1/../../webops.config.json",
    ],
)
def test_report_path_traversal_rejected(client, settings, path):
    resp = client.get(path)
    assert resp.status_code in (400, 404)
    assert "webops" not in (resp.text or "")


def test_report_resolve_traversal_400(tmp_path):
    service = ReportService(tmp_path / "reports")
    with pytest.raises(Exception) as exc_info:
        service.resolve("../outside.txt")
    assert exc_info.value.status_code == 400


def test_report_resolve_empty_400(tmp_path):
    service = ReportService(tmp_path / "reports")
    with pytest.raises(Exception) as exc_info:
        service.resolve("")
    assert exc_info.value.status_code == 400


# ------------------------------------------------------------- 执行报告接口（7.3）

def test_run_report_running_marker(client, session):
    tree = create_tree(client)
    run = Run(tree_id=tree["id"], status="running")
    session.add(run)
    session.commit()
    resp = client.get(f"/api/runs/{run.id}/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert "尚未完成" in body["message"]


def test_run_report_done(client, session, settings):
    tree = create_tree(client)
    resp = client.post(f"/api/trees/{tree['id']}/run")
    run_id = resp.json()["run_id"]
    _write_report_file(settings, run_id, "exec_report.md", "# 执行报告\n全部节点成功")
    _write_report_file(settings, run_id, "trace_report.md", "# 回溯报告\nLLM 推理")
    assert session.get(Run, run_id).status == "success"

    report = client.get(f"/api/runs/{run_id}/report")
    assert report.status_code == 200
    assert report.text == "# 执行报告\n全部节点成功"

    trace = client.get(f"/api/runs/{run_id}/trace")
    assert trace.status_code == 200
    assert trace.text == "# 回溯报告\nLLM 推理"


def test_report_path_persisted_from_result(client, mock_engine, session, settings):
    """任务 7.1：执行结果携带报告路径 → 相对路径入库。"""
    from webops.orchestrator.models import RunResult
    from webops.reporting import ExecReport, TraceReport

    tree = create_tree(client)
    _write_report_file(settings, 1, "exec_report.md", "# 执行报告")
    _write_report_file(settings, 1, "trace_report.md", "# 回溯报告")
    mock_engine.default_result = RunResult(
        status="success",
        exec_report=ExecReport(
            run_id="1", path=str(settings.report_root / "1" / "exec_report.md")
        ),
        trace_report=TraceReport(
            run_id="1", path=str(settings.report_root / "1" / "trace_report.md")
        ),
    )
    resp = client.post(f"/api/trees/{tree['id']}/run")
    run_id = resp.json()["run_id"]
    assert run_id == 1
    run = session.get(Run, run_id)
    assert run.status == "success"
    assert run.report_path == f"{run_id}/exec_report.md"


def test_run_report_missing_file_404(client, session):
    tree = create_tree(client)
    resp = client.post(f"/api/trees/{tree['id']}/run")
    run_id = resp.json()["run_id"]
    assert session.get(Run, run_id).status == "success"
    assert client.get(f"/api/runs/{run_id}/report").status_code == 404


def test_run_report_missing_run_404(client):
    assert client.get("/api/runs/999/report").status_code == 404
    assert client.get("/api/runs/999/trace").status_code == 404
