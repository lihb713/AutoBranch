"""插件管理 API 测试（组 6.1/6.2）：builtin 初始化 / CRUD / 校验 / 删除保留引用。"""

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
      y: int
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
    assert "browser.semantic_graph" not in browser["functions"]
    assert browser["custom_types"] == [
        {
            "token": "page_object",
            "class_name": "PageObject",
            "description": "页面对象（浏览器插件自定义类型 ``page_object`` 的值）。",
            "constructible": False,
        }
    ]


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
    assert "http.request" in names
    assert "compute.add" in names
    assert "browser.page_request" in names
    assert "browser.get_request_headers" in names
    assert "browser.get_header_value" in names
    # LLM-only 技术接口不进入用户函数清单
    assert "browser.semantic_graph" not in names
    assert "browser.get_response" not in names
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


TYPED_PLUGIN = """
class Widget:
    pass

class TypedDemo(PluginBase):
    name = "typeddemo"
    description = "带自定义类型的演示插件"

    @property
    def custom_types(self):
        return {"typeddemo_widget": Widget}

    @engine_function(
        name="make",
        description="造一个对象",
        returns={"w": "typeddemo_widget"},
    )
    def make(self):
        return Widget()

plugin = TypedDemo()
""".strip()


def test_custom_plugin_type_registers_and_unregisters(client):
    res = client.post("/api/plugins", json={"name": "typeddemo", "source": TYPED_PLUGIN})
    assert res.status_code == 201, res.text
    assert res.json()["custom_types"][0]["token"] == "typeddemo_widget"
    types = {t["token"]: t for t in client.get("/api/types").json()}
    assert types["typeddemo_widget"]["owner"] == "typeddemo"
    assert types["typeddemo_widget"]["custom"] is True
    assert types["typeddemo_widget"]["constructible"] is False
    listed = next(p for p in client.get("/api/plugins").json() if p["name"] == "typeddemo")
    assert listed["custom_types"][0]["token"] == "typeddemo_widget"

    assert client.delete("/api/plugins/typeddemo").status_code == 200
    assert "typeddemo_widget" not in {t["token"] for t in client.get("/api/types").json()}


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


def test_delete_plugin_keeps_references_for_reregistration(client):
    client.post("/api/plugins", json={"name": "demo", "source": VALID_PLUGIN})
    tree = client.post("/api/trees", json={"name": "引用树", "content": TREE_WITH_FC})
    assert tree.status_code == 201
    # 引用查询命中
    refs = client.get("/api/plugins/demo/references")
    assert refs.status_code == 200
    assert "引用树" in refs.json()
    # 删除 → 返回受影响树；行为树 FunctionCall 引用保留
    res = client.delete("/api/plugins/demo")
    assert res.status_code == 200
    assert res.json()["affected_trees"] == ["引用树"]
    updated = client.get(f"/api/trees/{tree.json()['id']}").json()["content"]
    assert "function: demo.double" in updated
    assert "function: null" not in updated


def test_delete_plugin_without_references(client):
    client.post("/api/plugins", json={"name": "demo", "source": VALID_PLUGIN})
    res = client.delete("/api/plugins/demo")
    assert res.status_code == 200
    assert res.json()["affected_trees"] == []
    assert client.get("/api/plugins/demo").status_code == 404
