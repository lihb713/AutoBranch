"""插件管理 API 测试（组 6.1/6.2）：builtin 初始化 / CRUD / 校验 / 删除置空。"""

from __future__ import annotations

VALID_PLUGIN = """
class Demo(PluginBase):
    name = "demo"
    description = "演示插件"

    @engine_function(name="double", description="翻倍")
    def double(self):
        return 42

plugin = Demo()
""".strip()

BAD_PLUGIN_IMPORT = """
import requests
plugin = None
""".strip()

TREE_WITH_FC = """
tree: 引用树
nodes:
  r:
    type: Root
    body: n1
  n1:
    type: FunctionCall
    function: demo.double
    args: []
    returns:
      NewParam.y: int
root: r
""".strip()


def test_list_plugins_includes_builtins(client):
    res = client.get("/api/plugins")
    assert res.status_code == 200
    data = res.json()
    names = {p["name"] for p in data}
    assert "browser" in names and "compute" in names
    browser = next(p for p in data if p["name"] == "browser")
    assert browser["kind"] == "builtin"
    assert "browser.open" in browser["functions"]


def test_builtin_detail_source_is_null(client):
    res = client.get("/api/plugins/browser")
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "builtin"
    assert "browser.open" in body["functions"]
    # 内置插件只读：详情返回文件系统源码供查看
    assert body["source"] is not None
    assert "BrowserPlugin" in body["source"]


def test_check_plugin_valid(client):
    res = client.post("/api/plugins/check", json={"name": "demo", "source": VALID_PLUGIN})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert res.json()["errors"] == []


def test_list_functions_endpoint(client):
    res = client.get("/api/functions")
    assert res.status_code == 200
    data = res.json()
    names = {f["full_name"] for f in data}
    assert "browser.open" in names
    assert "compute.add" in names
    browser_open = next(f for f in data if f["full_name"] == "browser.open")
    assert browser_open["plugin"] == "browser"
    assert browser_open["name"] == "open"


def test_check_plugin_rejects_third_party(client):
    res = client.post("/api/plugins/check", json={"name": "bad", "source": BAD_PLUGIN_IMPORT})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert body["errors"][0]["type"] == "constraint"
    assert body["errors"][0]["line"] is not None


def test_create_custom_plugin(client):
    res = client.post("/api/plugins", json={"name": "demo", "source": VALID_PLUGIN})
    assert res.status_code == 201
    body = res.json()
    assert body["kind"] == "custom"
    assert body["functions"] == ["demo.double"]
    detail = client.get("/api/plugins/demo")
    assert detail.status_code == 200
    assert detail.json()["source"] == VALID_PLUGIN


def test_create_builtin_name_conflict(client):
    res = client.post("/api/plugins", json={"name": "compute", "source": VALID_PLUGIN})
    assert res.status_code == 409


def test_create_plugin_with_underscore_name(client):
    source = VALID_PLUGIN.replace('name = "demo"', 'name = "my_plugin_test"')
    res = client.post("/api/plugins", json={"name": "my_plugin_test", "source": source})
    assert res.status_code == 201
    assert res.json()["name"] == "my_plugin_test"


def test_builtin_readonly_rejected(client):
    res = client.put("/api/plugins/compute", json={"source": VALID_PLUGIN})
    assert res.status_code == 403
    res = client.delete("/api/plugins/compute")
    assert res.status_code == 403


def test_create_invalid_plugin_422(client):
    res = client.post("/api/plugins", json={"name": "bad", "source": BAD_PLUGIN_IMPORT})
    assert res.status_code == 422
    assert res.json()["detail"]["errors"]


def test_update_reloads_plugin(client):
    client.post("/api/plugins", json={"name": "demo", "source": VALID_PLUGIN})
    updated = VALID_PLUGIN.replace('description = "演示插件"', 'description = "升级版"')
    res = client.put("/api/plugins/demo", json={"source": updated})
    assert res.status_code == 200
    assert client.get("/api/plugins/demo").json()["description"] == "升级版"


def test_delete_plugin_nullifies_references(client):
    client.post("/api/plugins", json={"name": "demo", "source": VALID_PLUGIN})
    tree = client.post("/api/trees", json={"name": "引用树", "content": TREE_WITH_FC})
    assert tree.status_code == 201
    # 引用查询命中
    refs = client.get("/api/plugins/demo/references")
    assert refs.status_code == 200
    assert "引用树" in refs.json()
    # 删除 → 返回受影响树；行为树 FunctionCall 引用置空
    res = client.delete("/api/plugins/demo")
    assert res.status_code == 200
    assert res.json()["affected_trees"] == ["引用树"]
    updated = client.get(f"/api/trees/{tree.json()['id']}").json()["content"]
    assert "function: null" in updated
    assert "function: demo.double" not in updated


def test_delete_plugin_without_references(client):
    client.post("/api/plugins", json={"name": "demo", "source": VALID_PLUGIN})
    res = client.delete("/api/plugins/demo")
    assert res.status_code == 200
    assert res.json()["affected_trees"] == []
    assert client.get("/api/plugins/demo").status_code == 404
