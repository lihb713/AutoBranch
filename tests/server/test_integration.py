"""M9b 集成测试（任务 8.1，``pytest -m integration``）。

真实/半真实链路：内嵌真实 M7 引擎（注入 mock 浏览器 + mock 叶子执行器，
不启动真实浏览器/LLM）跑通 建文档 → 保存校验 → 触发执行 → 轮询至 finished
→ 取执行报告/回溯报告/报告文件。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from orchestrator_helpers import MockBrowser, StubLeaf

from webops.config import WebOpsConfig
from webops.orchestrator import Engine
from webops.server.config import ServerConfig
from webops.server.main import create_app
from webops.server.services.engine import EmbeddedEngineService, build_reporter_factory

from .conftest import VALID_YAML, make_tree_yaml

pytestmark = pytest.mark.integration


def _make_client(settings: ServerConfig) -> TestClient:
    def factory(run_id, report_root):
        return Engine(
            browser=MockBrowser(),
            leaf_executor=StubLeaf(),
            reporter_factory=build_reporter_factory(run_id, report_root),
        )

    engine_service = EmbeddedEngineService(
        WebOpsConfig.load(), settings.report_root, engine_factory=factory
    )
    app = create_app(settings, engine_service=engine_service)
    return TestClient(app)


def test_end_to_end_execution_flow(tmp_path):
    settings = ServerConfig(db_path=tmp_path / "webops.db", report_root=tmp_path / "reports")
    client = _make_client(settings)

    created = client.post("/api/trees", json={"name": "冒烟流程", "content": VALID_YAML})
    assert created.status_code == 201, created.text
    tree_id = created.json()["id"]

    check = client.post(f"/api/trees/{tree_id}/check")
    assert check.status_code == 200
    assert check.json()["ok"] is True

    run = client.post(f"/api/trees/{tree_id}/run")
    assert run.status_code == 202, run.text
    run_id = run.json()["run_id"]

    state = client.get(f"/api/runs/{run_id}/state")
    assert state.status_code == 200
    body = state.json()
    assert body["finished"] is True
    assert body["failure_reason"] is None
    assert body["progress"] == 1.0
    assert any(nr["node_type"] == "Action" for nr in body["completed"])

    report = client.get(f"/api/runs/{run_id}/report")
    assert report.status_code == 200
    assert '点"登录"' in report.text

    trace = client.get(f"/api/runs/{run_id}/trace")
    assert trace.status_code == 200
    assert "回溯" in trace.text

    file_resp = client.get(f"/api/reports/{run_id}/exec_report.md")
    assert file_resp.status_code == 200
    assert file_resp.text == report.text

    tree_list = client.get("/api/trees").json()
    assert tree_list[0]["name"] == "冒烟流程"


def test_run_after_rename_matches_content_root_block(tmp_path):
    """回归：改名后主块名=树名（强制一致），doc_id 对齐后运行成功。"""
    settings = ServerConfig(db_path=tmp_path / "webops.db", report_root=tmp_path / "reports")
    client = _make_client(settings)

    created = client.post("/api/trees", json={"name": "我的流程", "content": make_tree_yaml("我的流程")})
    assert created.status_code == 201
    tree_id = created.json()["id"]

    renamed = client.put(
        f"/api/trees/{tree_id}",
        json={"name": "改名后的流程", "content": make_tree_yaml("改名后的流程")},
    )
    assert renamed.status_code == 200

    run = client.post(f"/api/trees/{tree_id}/run")
    assert run.status_code == 202
    run_id = run.json()["run_id"]

    state = client.get(f"/api/runs/{run_id}/state").json()
    assert state["finished"] is True
    assert state["failure_reason"] is None
    assert any(nr["node_type"] == "Action" for nr in state["completed"])


def test_end_to_end_execution_failure_flow(tmp_path):
    """执行前校验拦截：损坏文档触发执行返回 422 且不产生 run。"""
    settings = ServerConfig(db_path=tmp_path / "webops.db", report_root=tmp_path / "reports")
    client = _make_client(settings)

    from webops.server.db import configure_database, session_factory
    from webops.server.models import Run, Tree

    configure_database(settings.db_path)
    db = session_factory()()
    tree = Tree(name="坏文档", content="block 坏文档:\n  Sequence:\n    - ref: this/不存在的块\n")
    db.add(tree)
    db.commit()
    db.refresh(tree)
    tree_id = tree.id
    db.close()

    resp = client.post(f"/api/trees/{tree_id}/run")
    assert resp.status_code == 422
    assert "ref" in resp.text

    configure_database(settings.db_path)
    db = session_factory()()
    assert db.query(Run).count() == 0
    db.close()
