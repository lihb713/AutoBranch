"""文件管理平台目录/路径能力 API 测试。"""

from __future__ import annotations

import hashlib
import io
import uuid
import zipfile


def _name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def test_directory_crud_and_path_file_upload(client):
    root = _name("dir")
    nested = f"{root}/2026"
    created = client.post("/api/plugins/file/directories", json={"path": nested})
    assert created.status_code == 200, created.text
    assert created.json()["path"] == nested

    entries = client.get("/api/plugins/file/entries").json()
    assert any(d["path"] == root for d in entries["directories"])

    upload = client.post(
        "/api/plugins/file/files",
        data={"path": f"{nested}/report.txt"},
        files={"file": ("report.txt", b"hello-dir", "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    record = upload.json()
    assert record["path"] == f"{nested}/report.txt"
    assert record["md5"] == hashlib.md5(b"hello-dir").hexdigest()

    entries = client.get("/api/plugins/file/entries", params={"path": nested}).json()
    assert any(f["path"] == record["path"] for f in entries["files"])

    download = client.get("/api/plugins/file/download", params={"path": record["path"]})
    assert download.status_code == 200
    assert download.content == b"hello-dir"

    conflict = client.post(
        "/api/plugins/file/files",
        data={"path": record["path"]},
        files={"file": ("report.txt", b"again", "text/plain")},
    )
    assert conflict.status_code == 409

    renamed_path = f"{_name('archive')}/2026"
    renamed = client.put(
        f"/api/plugins/file/directories/{created.json()['id']}",
        json={"path": renamed_path},
    )
    assert renamed.status_code == 200, renamed.text
    moved = client.get(
        "/api/plugins/file/download", params={"path": f"{renamed_path}/report.txt"}
    )
    assert moved.status_code == 200
    assert moved.content == b"hello-dir"

    deleted = client.delete(f"/api/plugins/file/directories/{created.json()['id']}")
    assert deleted.status_code == 200
    assert (
        client.get(
            "/api/plugins/file/download", params={"path": f"{renamed_path}/report.txt"}
        ).status_code
        == 404
    )


def test_download_directory_as_zip(client):
    root = _name("zip")
    assert (
        client.post("/api/plugins/file/directories", json={"path": f"{root}/sub"}).status_code
        == 200
    )
    for name, content in (("a.txt", b"A"), ("sub/b.txt", b"B")):
        resp = client.post(
            "/api/plugins/file/files",
            data={"path": f"{root}/{name}"},
            files={"file": (name.rsplit("/", 1)[-1], content, "text/plain")},
        )
        assert resp.status_code == 200, resp.text

    download = client.get("/api/plugins/file/download", params={"path": root})
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    names = set(archive.namelist())
    assert f"{root}/a.txt" in names
    assert f"{root}/sub/b.txt" in names

    # 清理根目录（按目录 id 删除）
    dirs = client.get("/api/plugins/file/directories").json()
    root_dir = next(d for d in dirs if d["path"] == root)
    assert client.delete(f"/api/plugins/file/directories/{root_dir['id']}").status_code == 200
