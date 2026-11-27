"""行为树分组 API：默认分组、CRUD、移动与删除约束。"""

from __future__ import annotations

from .conftest import create_tree


def _default_group(client):
    groups = client.get("/api/tree-groups").json()
    return next(group for group in groups if group["is_default"])


def test_default_group_exists_and_tree_defaults_to_it(client):
    groups = client.get("/api/tree-groups")
    assert groups.status_code == 200
    default = _default_group(client)
    assert default["name"] == "默认分组"

    tree = create_tree(client, name="默认分组树")
    assert tree["group_id"] == default["id"]
    assert tree["group_name"] == "默认分组"


def test_group_crud_and_tree_move(client):
    tree = create_tree(client, name="待移动树")
    created = client.post("/api/tree-groups", json={"name": "生产环境"})
    assert created.status_code == 201, created.text
    group = created.json()
    assert group["tree_count"] == 0

    moved = client.patch(
        f"/api/trees/{tree['id']}/group", json={"group_id": group["id"]}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["group_id"] == group["id"]
    assert moved.json()["group_name"] == "生产环境"
    assert client.get(f"/api/trees?group_id={group['id']}").json()[0]["id"] == tree["id"]

    renamed = client.put(
        f"/api/tree-groups/{group['id']}", json={"name": "生产组"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "生产组"
    assert renamed.json()["tree_count"] == 1

    blocked = client.delete(f"/api/tree-groups/{group['id']}")
    assert blocked.status_code == 409

    default = _default_group(client)
    client.patch(f"/api/trees/{tree['id']}/group", json={"group_id": default["id"]})
    deleted = client.delete(f"/api/tree-groups/{group['id']}")
    assert deleted.status_code == 204


def test_default_group_cannot_delete_and_duplicate_name_rejected(client):
    default = _default_group(client)
    assert client.delete(f"/api/tree-groups/{default['id']}").status_code == 403
    client.post("/api/tree-groups", json={"name": "重复组"})
    dup = client.post("/api/tree-groups", json={"name": "重复组"})
    assert dup.status_code == 409
