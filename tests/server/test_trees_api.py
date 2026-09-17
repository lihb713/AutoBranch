"""行为树文档 CRUD API 测试（任务 3.3）与保存路径校验（任务 4.2）。

用 ``fastapi.testclient.TestClient``（testing-guidelines.md §2）。
"""

from __future__ import annotations

from autobranch.server.models import Run, Tree

from .conftest import INVALID_REF_YAML, VALID_YAML, create_tree, make_tree_yaml


def test_list_trees_empty(client):
    resp = client.get("/api/trees")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_trees(client):
    create_tree(client, name="登录流程")
    create_tree(client, name="下单流程")
    resp = client.get("/api/trees")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert {item["name"] for item in items} == {"登录流程", "下单流程"}
    assert all({"id", "name", "created_at", "updated_at"} <= set(item) for item in items)


def test_get_tree(client):
    tree = create_tree(client)
    resp = client.get(f"/api/trees/{tree['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == tree["id"]
    assert body["content"] == make_tree_yaml("冒烟流程")


def test_get_tree_missing_404(client):
    resp = client.get("/api/trees/999")
    assert resp.status_code == 404


def test_get_tree_by_name(client):
    tree = create_tree(client, name="登录流程")
    resp = client.get(f"/api/trees/by-name/{tree['name']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "登录流程"
    assert resp.json()["id"] == tree["id"]


def test_get_tree_by_name_missing_404(client):
    resp = client.get("/api/trees/by-name/不存在的文档")
    assert resp.status_code == 404


def test_update_tree(client):
    tree = create_tree(client)
    resp = client.put(
        f"/api/trees/{tree['id']}",
        json={"name": "改名流程", "content": make_tree_yaml("改名流程")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "改名流程"
    detail = client.get(f"/api/trees/{tree['id']}").json()
    assert detail["content"] == make_tree_yaml("改名流程")


def test_update_content_only(client):
    tree = create_tree(client)
    resp = client.put(f"/api/trees/{tree['id']}", json={"content": make_tree_yaml("冒烟流程")})
    assert resp.status_code == 200
    assert resp.json()["name"] == "冒烟流程"


def test_update_missing_404(client):
    resp = client.put("/api/trees/999", json={"name": "x", "content": VALID_YAML})
    assert resp.status_code == 404


def test_update_empty_payload_422(client):
    tree = create_tree(client)
    resp = client.put(f"/api/trees/{tree['id']}", json={})
    assert resp.status_code == 422


def test_delete_tree(client, session):
    tree = create_tree(client)
    resp = client.delete(f"/api/trees/{tree['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/trees/{tree['id']}").status_code == 404


def test_delete_missing_404(client):
    resp = client.delete("/api/trees/999")
    assert resp.status_code == 404


def test_delete_tree_cascades_runs_and_files(client, session, settings):
    tree = create_tree(client)
    run = Run(tree_id=tree["id"], status="success", report_path="1/exec_report.md")
    session.add(run)
    session.commit()
    report_dir = settings.report_root / "1"
    report_dir.mkdir(parents=True)
    (report_dir / "exec_report.md").write_text("报告", encoding="utf-8")

    resp = client.delete(f"/api/trees/{tree['id']}")
    assert resp.status_code == 204
    assert not report_dir.exists()
    from autobranch.server.db import session_factory

    fresh = session_factory()()
    assert fresh.get(Run, run.id) is None
    fresh.close()


def test_create_duplicate_409(client):
    create_tree(client, name="登录流程")
    resp = client.post(
        "/api/trees", json={"name": "登录流程", "content": make_tree_yaml("登录流程")}
    )
    assert resp.status_code == 409
    assert len(client.get("/api/trees").json()) == 1


def test_create_empty_name_422(client):
    resp = client.post("/api/trees", json={"name": "", "content": VALID_YAML})
    assert resp.status_code == 422


def test_create_long_name_422(client):
    resp = client.post(
        "/api/trees",
        json={"name": "x" * 201, "content": VALID_YAML},
    )
    assert resp.status_code == 422


def test_create_missing_content_422(client):
    resp = client.post("/api/trees", json={"name": "无内容"})
    assert resp.status_code == 422


# ----------------------------------------------------------- 保存路径校验（4.2）

def test_create_invalid_document_422_not_saved(client):
    resp = client.post("/api/trees", json={"name": "坏文档", "content": INVALID_REF_YAML})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any(item["code"].startswith("ref") for item in detail)
    assert client.get("/api/trees").json() == []


def test_update_invalid_document_422_not_saved(client):
    tree = create_tree(client)
    resp = client.put(
        f"/api/trees/{tree['id']}",
        json={"name": "坏文档", "content": INVALID_REF_YAML},
    )
    assert resp.status_code == 422
    detail = client.get(f"/api/trees/{tree['id']}").json()
    assert detail["name"] == "冒烟流程"
    assert detail["content"] == make_tree_yaml("冒烟流程")


def test_check_endpoint_ok(client):
    tree = create_tree(client)
    resp = client.post(f"/api/trees/{tree['id']}/check")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "issues": []}


def test_check_endpoint_invalid(client, session):
    tree = create_tree(client)
    db_tree = session.get(Tree, tree["id"])
    db_tree.content = INVALID_REF_YAML
    session.commit()
    resp = client.post(f"/api/trees/{tree['id']}/check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert any(issue["code"].startswith("ref") for issue in body["issues"])


def test_check_missing_tree_404(client):
    resp = client.post("/api/trees/999/check")
    assert resp.status_code == 404
