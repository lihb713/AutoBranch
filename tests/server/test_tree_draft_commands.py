"""后端权威文档：草稿/正式、命令编辑、默认接收名、ref 仅正式版。"""

from __future__ import annotations

import yaml

from .conftest import create_tree


def _content(client, tree_id: int) -> str:
    return client.get(f"/api/trees/{tree_id}").json()["content"]


def _add_fc(client, tree_id: int, *, function: str | None = None) -> tuple[str, str]:
    resp = client.post(
        f"/api/trees/{tree_id}/commands",
        json={"commands": [{"op": "add_node", "node_type": "FunctionCall"}]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    node_id = body["created_node_id"]
    if function:
        resp = client.post(
            f"/api/trees/{tree_id}/commands",
            json={
                "commands": [
                    {
                        "op": "update_node",
                        "node_id": node_id,
                        "patch": {
                            "function": function,
                            "args": ["GET", "http://127.0.0.1:8123/index.html"],
                        },
                    },
                    {"op": "set_slot", "node_id": "n1", "slot_index": 0, "child_id": node_id},
                ]
            },
        )
        assert resp.status_code == 200, resp.text
    return node_id, _content(client, tree_id)


def test_new_draft_and_save_publish(client):
    draft = client.post("/api/trees/drafts").json()
    assert draft["status"] == "draft"
    assert draft["name"].startswith("未命名-")

    resp = client.post(
        f"/api/trees/{draft['id']}/commands",
        json={
            "commands": [
                {"op": "add_node", "node_type": "Action"},
                {
                    "op": "update_node",
                    "node_id": "n2",
                    "patch": {"description": "点击登录"},
                },
                {"op": "set_slot", "node_id": "n1", "slot_index": 0, "child_id": "n2"},
            ]
        },
    )
    assert resp.status_code == 200
    saved = client.post(f"/api/trees/{draft['id']}/save", json={"name": "正式流程"})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["status"] == "published"
    assert body["name"] == "正式流程"
    assert "tree: 正式流程" in body["content"]


def test_function_default_names_and_types(client):
    draft = client.post("/api/trees/drafts").json()
    _node, content = _add_fc(client, draft["id"], function="http.request")
    data = yaml.safe_load(content)
    returns = data["nodes"]["n2"]["returns"]
    assert returns == {
        "n2_status": "int",
        "n2_body": "str",
        "n2_headers": "object",
    }


def test_conflict_suffix_starts_at_one(client):
    draft = client.post("/api/trees/drafts").json()
    client.post(
        f"/api/trees/{draft['id']}/commands",
        json={"commands": [{"op": "update_doc", "patch": {"inputs": {"n2_status": "str"}}}]},
    )
    _node, content = _add_fc(client, draft["id"], function="http.request")
    returns = yaml.safe_load(content)["nodes"]["n2"]["returns"]
    assert list(returns)[:1] == ["n2_status_1"]
    # 删除冲突变量后不回退原名
    client.post(
        f"/api/trees/{draft['id']}/commands",
        json={"commands": [{"op": "update_doc", "patch": {"inputs": {}}}]},
    )
    returns = yaml.safe_load(_content(client, draft["id"]))["nodes"]["n2"]["returns"]
    assert "n2_status_1" in returns


def test_type_follows_function_and_name_preserved(client):
    draft = client.post("/api/trees/drafts").json()
    client.post(
        f"/api/trees/{draft['id']}/commands",
        json={"commands": [{"op": "add_node", "node_type": "FunctionCall"}]},
    )
    # 先选返回 url:str 的函数，改名 custom
    client.post(
        f"/api/trees/{draft['id']}/commands",
        json={
            "commands": [
                {
                    "op": "update_node",
                    "node_id": "n2",
                    "patch": {"function": "browser.get_url", "returns": {"custom": "str"}},
                }
            ]
        },
    )
    returns = yaml.safe_load(_content(client, draft["id"]))["nodes"]["n2"]["returns"]
    assert returns == {"custom": "str"}
    # 换函数：手写名 custom 保留，类型随新函数刷新
    client.post(
        f"/api/trees/{draft['id']}/commands",
        json={
            "commands": [
                {
                    "op": "update_node",
                    "node_id": "n2",
                    "patch": {"function": "http.request", "args": ["GET", "http://x"]},
                }
            ]
        },
    )
    returns = yaml.safe_load(_content(client, draft["id"]))["nodes"]["n2"]["returns"]
    assert returns["custom"] == "int"


def test_auto_rename_does_not_rewrite_references(client):
    draft = client.post("/api/trees/drafts").json()
    client.post(
        f"/api/trees/{draft['id']}/commands",
        json={"commands": [{"op": "add_node", "node_type": "Action"}]},
    )
    client.post(
        f"/api/trees/{draft['id']}/commands",
        json={
            "commands": [
                {
                    "op": "update_node",
                    "node_id": "n2",
                    "patch": {"description": "使用 Param.n2_url 的值"},
                },
                {"op": "add_node", "node_type": "FunctionCall"},
            ]
        },
    )
    # 首次选 get_url → n3_url
    client.post(
        f"/api/trees/{draft['id']}/commands",
        json={
            "commands": [
                {"op": "update_node", "node_id": "n3", "patch": {"function": "browser.get_url"}}
            ]
        },
    )
    # 换成 http_request → 自动名从 n3_url 变 n3_status...，但 Action 引用不改写
    client.post(
        f"/api/trees/{draft['id']}/commands",
        json={
            "commands": [
                {
                    "op": "update_node",
                    "node_id": "n3",
                    "patch": {"function": "http.request", "args": ["GET", "http://x"]},
                }
            ]
        },
    )
    data = yaml.safe_load(_content(client, draft["id"]))
    assert "Param.n2_url" in data["nodes"]["n2"]["description"]
    assert "n3_url" not in data["nodes"]["n3"]["returns"]


def test_published_edit_becomes_draft_and_cannot_run(client):
    tree = create_tree(client, name="正式树")
    assert tree["status"] == "published"
    resp = client.post(
        f"/api/trees/{tree['id']}/commands",
        json={"commands": [{"op": "add_node", "node_type": "Action"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["tree"]["status"] == "draft"
    run = client.post(f"/api/trees/{tree['id']}/run")
    assert run.status_code == 409


def test_ref_target_draft_rejected(client):
    child = client.post(
        "/api/trees",
        json={
            "name": "子流程",
            "content": (
                "tree: 子流程\n"
                "outputs: {urlText: str}\n"
                "nodes:\n"
                "  n1: {type: Root, body: n2}\n"
                '  n2: {type: Action, description: "记录 NewParam.urlText:str"}\n'
                "root: n1\n"
            ),
        },
    ).json()
    assert child["status"] == "draft"
    parent = client.post(
        "/api/trees/drafts",
    ).json()
    client.post(
        f"/api/trees/{parent['id']}/commands",
        json={
            "commands": [
                {"op": "add_node", "node_type": "ref"},
                {
                    "op": "update_node",
                    "node_id": "n2",
                    "patch": {"target": "子流程"},
                },
                {"op": "set_slot", "node_id": "n1", "slot_index": 0, "child_id": "n2"},
            ]
        },
    )
    save = client.post(f"/api/trees/{parent['id']}/save", json={"name": "父流程"})
    assert save.status_code == 422
    assert any("正式版" in item["message"] for item in save.json()["detail"])

    # 子流程发布后，父流程可保存
    assert client.post(f"/api/trees/{child['id']}/save").status_code == 200
    assert (
        client.post(f"/api/trees/{parent['id']}/save", json={"name": "父流程"}).status_code
        == 200
    )


def test_run_fallback_normalizes_missing_returns(client, session):
    from autobranch.server.models import Run, Tree

    tree = create_tree(client, name="运行兜底")
    db_tree = session.get(Tree, tree["id"])
    db_tree.content = (
        "tree: 运行兜底\n"
        "nodes:\n"
        "  n1: {type: Root, body: n2}\n"
        "  n2:\n"
        "    type: FunctionCall\n"
        "    function: http.request\n"
        '    args: ["GET", "http://x"]\n'
        "root: n1\n"
    )
    session.commit()
    resp = client.post(f"/api/trees/{tree['id']}/run")
    assert resp.status_code == 202
    run = session.get(Run, resp.json()["run_id"])
    assert "n2_status" in run.content_snapshot
    assert "n2_body" in run.content_snapshot
