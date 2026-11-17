"""M10 调度 API 测试（CRUD / 依赖环 / 立即执行 / 来源过滤）。"""

from __future__ import annotations

import time

from .conftest import create_tree


def _schedule_payload(tree_id: int, **overrides):
    payload = {
        "name": "每日流程",
        "target_tree_id": tree_id,
        "schedule_mode": "interval",
        "interval": 30,
        "interval_unit": "minutes",
        "dependencies": [],
        "on_failure": "immediate",
        "max_retries": 3,
        "retry_interval": 60,
        "on_missed": "run",
        "inputs": {},
        "enabled": True,
    }
    payload.update(overrides)
    return payload


def _wait_run(client, run_id: int, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    body: dict = {}
    while time.time() < deadline:
        body = client.get(f"/api/runs/{run_id}/state").json()
        if body.get("finished"):
            return body
        time.sleep(0.02)
    return body


def test_schedule_crud_and_run_now(client):
    tree = create_tree(client, "调度目标")
    created = client.post("/api/schedules", json=_schedule_payload(tree["id"]))
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["target_tree_name"] == "调度目标"
    assert rule["schedule_mode"] == "interval"
    assert rule["enabled"] is True
    assert rule["last_run_at"] is None

    listed = client.get("/api/schedules")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [rule["id"]]

    updated = client.put(
        f"/api/schedules/{rule['id']}",
        json=_schedule_payload(
            tree["id"],
            name="改名调度",
            schedule_mode="cron",
            cron_period="day",
            cron_time="21:00",
            interval=None,
            interval_unit=None,
        ),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "改名调度"
    assert updated.json()["cron_time"] == "21:00"

    toggled = client.patch(f"/api/schedules/{rule['id']}/toggle")
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is False
    client.patch(f"/api/schedules/{rule['id']}/toggle")

    run_now = client.post(f"/api/schedules/{rule['id']}/run")
    assert run_now.status_code == 202, run_now.text
    run_id = run_now.json()["run_id"]
    assert _wait_run(client, run_id)["finished"] is True

    runs = client.get(f"/api/runs?schedule_id={rule['id']}").json()
    assert [item["id"] for item in runs] == [run_id]
    assert runs[0]["source"] == "schedule"
    assert runs[0]["schedule_id"] == rule["id"]

    records = client.get(f"/api/schedules/{rule['id']}/runs")
    assert records.status_code == 200
    assert records.json()[0]["id"] == run_id

    deleted = client.delete(f"/api/schedules/{rule['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/schedules").json() == []


def test_schedule_cycle_rejected(client):
    a = create_tree(client, "树A")
    b = create_tree(client, "树B")
    first = client.post(
        "/api/schedules",
        json=_schedule_payload(a["id"], name="A调度", dependencies=[b["id"]]),
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/api/schedules",
        json=_schedule_payload(b["id"], name="B调度", dependencies=[a["id"]]),
    )
    assert second.status_code == 422
    assert "循环" in second.text


def test_schedule_rejects_non_constructible_inputs(client):
    page_tree = create_tree(
        client,
        "页签树",
        content="""
tree: 页签树
inputs:
  page: page_ref
nodes:
  n1:
    type: Root
    body: n2
  n2:
    type: Action
    description: 操作 Param.page
root: n1
""".strip(),
    )
    resp = client.post("/api/schedules", json=_schedule_payload(page_tree["id"]))
    assert resp.status_code == 422
    assert "不可由文本构造" in resp.text


def test_schedule_rejects_draft_target(client):
    draft = client.post(
        "/api/trees",
        json={
            "name": "草稿目标",
            "content": """
tree: 草稿目标
nodes:
  n1:
    type: Root
    body: n2
  n2:
    type: Action
    description: 操作
root: n1
""".strip(),
        },
    ).json()
    resp = client.post("/api/schedules", json=_schedule_payload(draft["id"]))
    assert resp.status_code == 409
    assert "草稿" in resp.text


def test_schedule_cron_validation(client):
    tree = create_tree(client, "定时目标")
    resp = client.post(
        "/api/schedules",
        json=_schedule_payload(
            tree["id"],
            schedule_mode="cron",
            cron_period="week",
            cron_time="07:00",
            interval=None,
            interval_unit=None,
        ),
    )
    assert resp.status_code == 422
    assert "星期" in resp.text
