"""执行触发 / 状态轮询 / 重启恢复 API 测试（任务 5.2/5.3/6.1/6.2）。"""

from __future__ import annotations

from webops.orchestrator.models import RunResult
from webops.reporting import ActionCall, ExecState, NodeInfo, NodeReport
from webops.server.db import configure_database, session_factory
from webops.server.main import create_app
from webops.server.models import Run, Tree

from .conftest import INVALID_REF_YAML, create_tree, make_tree_yaml

# ------------------------------------------------------------- 触发（5.2）

def test_run_returns_202_and_state_success(client, mock_engine):
    tree = create_tree(client)
    resp = client.post(f"/api/trees/{tree['id']}/run")
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    state = client.get(f"/api/runs/{run_id}/state").json()
    assert state["finished"] is True
    assert state["progress"] == 1.0
    assert state["failure_reason"] is None
    assert mock_engine.call_log == [(tree["id"], make_tree_yaml("冒烟流程"), run_id)]


def test_run_failure_writes_reason(client, mock_engine, session):
    mock_engine.default_result = RunResult(status="failure", failure_reason="脚本失败")
    tree = create_tree(client)
    resp = client.post(f"/api/trees/{tree['id']}/run")
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    state = client.get(f"/api/runs/{run_id}/state").json()
    assert state["finished"] is True
    assert state["failure_reason"] == "脚本失败"
    run = session.get(Run, run_id)
    assert run.status == "failure"
    assert run.failure_reason == "脚本失败"


def test_run_missing_tree_404(client):
    resp = client.post("/api/trees/999/run")
    assert resp.status_code == 404


# ------------------------------------------------------------- 执行前校验（4.3）

def test_run_invalid_document_422_no_run(client, session):
    tree = create_tree(client)
    db_tree = session.get(Tree, tree["id"])
    db_tree.content = INVALID_REF_YAML
    session.commit()
    resp = client.post(f"/api/trees/{tree['id']}/run")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any(item["code"].startswith("ref") for item in detail)
    assert session.query(Run).count() == 0


# ------------------------------------------------------------- 并发去重（5.3）

def test_concurrent_run_409_and_single_record(client, session):
    tree = create_tree(client)
    run = Run(tree_id=tree["id"], status="running")
    session.add(run)
    session.commit()

    resp = client.post(f"/api/trees/{tree['id']}/run")
    assert resp.status_code == 409
    assert "进行中" in resp.json()["detail"]
    assert session.query(Run).count() == 1


def test_consecutive_runs_allowed_after_finish(client):
    tree = create_tree(client)
    first = client.post(f"/api/trees/{tree['id']}/run")
    assert first.status_code == 202
    second = client.post(f"/api/trees/{tree['id']}/run")
    assert second.status_code == 202


# ------------------------------------------------------------- 状态轮询（6.1）

def test_state_polling_advances(client, mock_engine, session):
    tree = create_tree(client)
    run = Run(tree_id=tree["id"], status="running")
    session.add(run)
    session.commit()

    nr1 = NodeReport(
        node_type="Action",
        node_desc='点"登录"',
        result="success",
        timestamp="2026-01-01T00:00:00",
        action_call=ActionCall(function="click", success=True),
        screenshot_path=f"{run.id}/001_login.png",
    )
    nr2 = NodeReport(
        node_type="Condition",
        node_desc='出现"工作台"',
        result="success",
        timestamp="2026-01-01T00:00:01",
    )
    states = [
        ExecState(
            run_id=str(run.id),
            total_nodes=4,
            current_node=NodeInfo("Action", '点"登录"'),
            completed=[],
        ),
        ExecState(run_id=str(run.id), total_nodes=4, completed=[nr1]),
        ExecState(run_id=str(run.id), total_nodes=4, completed=[nr1, nr2], finished=True),
    ]
    mock_engine.set_script(run.id, states=states)

    first = client.get(f"/api/runs/{run.id}/state").json()
    assert first["finished"] is False
    assert first["progress"] == 0.0
    assert first["current_node"]["node_desc"] == '点"登录"'
    assert first["completed"] == []

    second = client.get(f"/api/runs/{run.id}/state").json()
    assert second["progress"] == 0.25
    assert second["completed"][0]["screenshot_path"] == f"{run.id}/001_login.png"

    third = client.get(f"/api/runs/{run.id}/state").json()
    assert third["finished"] is True
    assert third["progress"] == 1.0
    assert len(third["completed"]) == 2
    assert {nr["node_type"] for nr in third["completed"]} == {"Action", "Condition"}


def test_state_missing_404(client):
    resp = client.get("/api/runs/999/state")
    assert resp.status_code == 404


def test_state_contract_fields(client):
    tree = create_tree(client)
    resp = client.post(f"/api/trees/{tree['id']}/run")
    run_id = resp.json()["run_id"]
    state = client.get(f"/api/runs/{run_id}/state").json()
    expected = {
        "run_id", "progress", "current_node", "completed",
        "finished", "failure_reason", "variables",
    }
    assert set(state) == expected
    assert isinstance(state["progress"], float)
    assert 0.0 <= state["progress"] <= 1.0
    assert isinstance(state["variables"], list)


# ------------------------------------------------------------- 重启恢复（6.2）

def test_startup_marks_running_as_interrupted(tmp_path):
    from fastapi.testclient import TestClient

    from webops.server.config import ServerConfig
    from webops.server.services.engine import MockEngineService

    cfg = ServerConfig(db_path=tmp_path / "webops.db", report_root=tmp_path / "reports")
    configure_database(cfg.db_path)
    db = session_factory()()
    tree = Tree(name="重启用", content=make_tree_yaml("重启用"))
    db.add(tree)
    db.commit()
    db.refresh(tree)
    db.add(Run(tree_id=tree.id, status="running"))
    db.commit()
    run_id = db.query(Run).first().id
    db.close()

    app = create_app(cfg, engine_service=MockEngineService())
    client = TestClient(app)

    state = client.get(f"/api/runs/{run_id}/state").json()
    assert state["finished"] is True
    assert state["failure_reason"] == "interrupted"
