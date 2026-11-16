"""插件模块化：manifest / 配置 / 插件函数详情 / 文件管理 API。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from autobranch.server.main import create_app


def _plugin(client: TestClient, name: str) -> dict:
    return next(p for p in client.get("/api/plugins").json() if p["name"] == name)


def test_include_manifest_returns_frontend_pages_and_config(client):
    data = client.get("/api/plugins", params={"include_manifest": "true"}).json()
    file_plugin = next(p for p in data if p["name"] == "file")
    assert file_plugin["frontend_manifest"]["pages"][0] == {
        "route": "/file",
        "label": "文件管理",
        "component": "FileManager",
        "icon": "folder",
    }
    assert file_plugin["config_schema"][0]["key"] == "max_file_size"
    browser = next(p for p in data if p["name"] == "browser")
    assert browser["frontend_manifest"] is None


def test_manifest_and_config_endpoints(client):
    manifest = client.get("/api/plugins/file/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["frontend_manifest"]["pages"][0]["component"] == "FileManager"

    current = client.get("/api/plugins/file/config")
    assert current.status_code == 200
    assert current.json()["max_file_size"] == 10

    updated = client.put("/api/plugins/file/config", json={"max_file_size": 5})
    assert updated.status_code == 200
    assert updated.json()["max_file_size"] == 5
    assert client.get("/api/plugins/file/config").json()["max_file_size"] == 5


def test_plugin_functions_detail_includes_all_visibility(client):
    funcs = client.get("/api/plugins/file/functions").json()
    by_name = {f["name"]: f for f in funcs}
    assert by_name["read"]["returns"] == {"content": "str"}
    assert by_name["read"]["user_visible"] is True
    assert by_name["read"]["output_param"] is None
    # 浏览器插件详情包含 LLM-only 技术函数
    browser = client.get("/api/plugins/browser/functions").json()
    semantic = next(f for f in browser if f["name"] == "semantic_graph")
    assert semantic["user_visible"] is False


def test_file_upload_list_download_delete(client):
    upload = client.post(
        "/api/plugins/file/files",
        files={"file": ("hello.txt", b"hello-autobranch", "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    record = upload.json()
    assert record["filename"] == "hello.txt"
    assert record["size"] == len(b"hello-autobranch")

    files = client.get("/api/plugins/file/files").json()
    assert any(f["id"] == record["id"] for f in files)

    detail = client.get(f"/api/plugins/file/files/{record['id']}")
    assert detail.status_code == 200
    assert detail.json()["filename"] == "hello.txt"

    download = client.get(f"/api/plugins/file/files/{record['id']}/download")
    assert download.status_code == 200
    assert download.content == b"hello-autobranch"

    deleted = client.delete(f"/api/plugins/file/files/{record['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/plugins/file/files/{record['id']}").status_code == 404


def test_file_upload_size_limit(client):
    client.put("/api/plugins/file/config", json={"max_file_size": 1})
    too_big = b"x" * (1024 * 1024 + 1)
    resp = client.post(
        "/api/plugins/file/files",
        files={"file": ("big.bin", too_big, "application/octet-stream")},
    )
    assert resp.status_code == 413
    client.put("/api/plugins/file/config", json={"max_file_size": 10})


def test_plugin_config_persists_across_app_restart(settings):
    client = TestClient(create_app(settings))
    assert client.put("/api/plugins/file/config", json={"max_file_size": 7}).status_code == 200
    client.close()

    client2 = TestClient(create_app(settings))
    assert client2.get("/api/plugins/file/config").json()["max_file_size"] == 7
    client2.put("/api/plugins/file/config", json={"max_file_size": 10})
    client2.close()
