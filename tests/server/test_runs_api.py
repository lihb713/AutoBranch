"""执行触发 / 状态轮询 / 重启恢复 API 测试（任务 5.2/5.3/6.1/6.2）。"""

from __future__ import annotations

import time

from autobranch.orchestrator.models import RunResult
from autobranch.reporting import ActionCall, ExecState, NodeInfo, NodeReport
from autobranch.server.db import configure_database, session_factory
from autobranch.server.main import create_app
from autobranch.server.models import Run, Tree

from .conftest import INVALID_REF_YAML, create_tree, make_tree_yaml


def wait_finished(client, run_id: int, timeout: float = 5.0) -> dict:
    """轮询直到实例终态（队列异步执行，轮询存在竞态窗口）。"""
    deadline = time.time() + timeout
    state: dict = {}
    while time.time() < deadline:
        state = client.get(f"/api/runs/{run_id}/state").json()
        if state["finished"]:
            return state
        time.sleep(0.02)
    return state


# ------------------------------------------------------------- 触发（5.2）

def test_run_returns_202_and_state_success(client, mock_engine):
    tree = create_tree(client)
    resp = client.post(f"/api/trees/{tree['id']}/run")
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    state = wait_finished(client, run_id)
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

    state = wait_finished(client, run_id)
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


# ------------------------------------------------------------- 队列调度（任务 3.3/4.2）

def test_concurrent_full_enters_queue(client, session):
    """并发满（3 个 running）时新触发进入排队（pending），不再 409。"""
    tree = create_tree(client)
    for _ in range(3):
        session.add(Run(tree_id=tree["id"], status="running"))
    session.commit()
    resp = client.post(f"/api/trees/{tree['id']}/run")
    assert resp.status_code == 202
    queued = session.query(Run).order_by(Run.id.desc()).first()
    assert queued.status == "pending"
    assert queued.content_snapshot  # 触发时刻冻结快照


def test_same_tree_multiple_runs_allowed(client):
    """同树可并发触发多个执行实例（无 D8 409 去重）。"""
    tree = create_tree(client)
    first = client.post(f"/api/trees/{tree['id']}/run")
    second = client.post(f"/api/trees/{tree['id']}/run")
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["run_id"] != second.json()["run_id"]


def test_consecutive_runs_allowed_after_finish(client):
    tree = create_tree(client)
    first = client.post(f"/api/trees/{tree['id']}/run")
    assert first.status_code == 202
    second = client.post(f"/api/trees/{tree['id']}/run")
    assert second.status_code == 202


# ------------------------------------------------------------- 入参/出参/列表/重试/删除（4.1-4.4）

_INPUTS_YAML = """
tree: 带参流程
inputs:
  user: str
  n: int
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: Action
    name: 动作
    description: 操作 Param.user
root: n1
""".strip()

_PAGE_REF_INPUT_YAML = """
tree: 页签流程
inputs:
  page: page_ref
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: Action
    name: 动作
    description: 操作 Param.page
root: n1
""".strip()


def _create(client, name: str, content: str) -> int:
    resp = client.post("/api/trees", json={"name": name, "content": content})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_run_with_inputs_stores_snapshot(client, mock_engine, session):
    tree_id = _create(client, "带参流程", _INPUTS_YAML)
    resp = client.post(f"/api/trees/{tree_id}/run", json={"inputs": {"user": "admin", "n": 7}})
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]
    run = session.get(Run, run_id)
    assert run.inputs == {"user": "admin", "n": 7}
    assert run.content_snapshot == _INPUTS_YAML.strip()
    assert run.tree_name_snapshot == "带参流程"
    assert run.tree_content_hash
    assert mock_engine.run_inputs_log[-1] == {"user": "admin", "n": 7}


def test_run_undeclared_input_422(client, session):
    tree_id = _create(client, "带参流程", _INPUTS_YAML)
    resp = client.post(f"/api/trees/{tree_id}/run", json={"inputs": {"x": "1"}})
    assert resp.status_code == 422
    assert "未声明的入参" in resp.json()["detail"]
    assert session.query(Run).count() == 0


def test_run_non_constructible_input_422(client, session):
    tree_id = _create(client, "页签流程", _PAGE_REF_INPUT_YAML)
    resp = client.post(f"/api/trees/{tree_id}/run")
    assert resp.status_code == 422
    assert "不可由文本构造" in resp.json()["detail"]
    assert session.query(Run).count() == 0


def test_list_runs_fields_and_order(client, mock_engine, session):
    tree_id = _create(client, "带参流程", _INPUTS_YAML)
    first = client.post(
        f"/api/trees/{tree_id}/run", json={"inputs": {"user": "a"}}
    ).json()["run_id"]
    second = client.post(
        f"/api/trees/{tree_id}/run", json={"inputs": {"user": "b"}}
    ).json()["run_id"]
    items = client.get("/api/runs").json()
    assert [it["id"] for it in items][:2] == [second, first]  # created_at 倒序
    item = items[0]
    assert item["tree_name"] == "带参流程"
    assert item["status"] in ("success", "failure", "running", "pending")
    assert item["inputs"] == {"user": "b"}
    assert item["tree_content_hash"]
    assert "duration" in item and "progress" in item


def test_retry_copies_snapshot_and_inputs(client, mock_engine, session):
    tree_id = _create(client, "带参流程", _INPUTS_YAML)
    original = client.post(
        f"/api/trees/{tree_id}/run", json={"inputs": {"user": "admin"}}
    ).json()["run_id"]
    resp = client.post(f"/api/runs/{original}/retry")
    assert resp.status_code == 202
    new_id = resp.json()["run_id"]
    src = session.get(Run, original)
    new = session.get(Run, new_id)
    assert new.content_snapshot == src.content_snapshot
    assert new.tree_content_hash == src.tree_content_hash
    assert new.inputs == src.inputs == {"user": "admin"}


def test_delete_run_removes_record_and_report(client, mock_engine, session, settings):
    tree_id = _create(client, "带参流程", _INPUTS_YAML)
    run_id = client.post(f"/api/trees/{tree_id}/run").json()["run_id"]
    report_dir = settings.report_root / str(run_id)
    report_dir.mkdir(parents=True)
    (report_dir / "exec_report.md").write_text("报告", encoding="utf-8")

    resp = client.delete(f"/api/runs/{run_id}")
    assert resp.status_code == 204
    assert session.get(Run, run_id) is None
    assert not report_dir.exists()


def test_types_api(client):
    types = {t["token"]: t for t in client.get("/api/types").json()}
    assert types["str"]["constructible"] is True
    assert types["int"]["constructible"] is True
    assert types["page_ref"]["constructible"] is False
    assert types["object"]["constructible"] is False


# ------------------------------------------------------------- 经验回灌采集（任务 4.1）

def test_api_run_success_collects_experience(client, mock_engine, session):
    from autobranch.reporting.models import ExecState as _ES
    from autobranch.reporting.models import LeafTrace as _LT
    from autobranch.reporting.models import NodeReport as _NR
    from autobranch.server.models import Experience

    tree_id = _create(client, "带参流程", _INPUTS_YAML)
    mock_engine.default_final_state = _ES(
        run_id="x",
        completed=[
            _NR(
                node_type="Action",
                node_desc="操作 admin",
                result="success",
                timestamp="t",
                llm_trace=_LT(
                    llm_input={"description": "操作 admin"},
                    decision="结果: 成功",
                ),
            )
        ],
    )
    resp = client.post(f"/api/trees/{tree_id}/run", json={"inputs": {"user": "admin"}})
    run_id = resp.json()["run_id"]
    wait_finished(client, run_id)
    rows = session.query(Experience).all()
    assert len(rows) == 1
    assert rows[0].node_desc == "操作 admin"


def test_api_run_failure_no_experience(client, mock_engine, session):
    from autobranch.server.models import Experience

    mock_engine.default_result = RunResult(status="failure", failure_reason="x")
    tree_id = _create(client, "带参流程", _INPUTS_YAML)
    resp = client.post(f"/api/trees/{tree_id}/run", json={"inputs": {"user": "admin"}})
    run_id = resp.json()["run_id"]
    wait_finished(client, run_id)
    assert session.query(Experience).count() == 0


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
    state = wait_finished(client, run_id)
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

    from autobranch.server.config import ServerConfig
    from autobranch.server.services.engine import MockEngineService

    cfg = ServerConfig(db_path=tmp_path / "autobranch.db", report_root=tmp_path / "reports")
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
