"""历史行为树迁移：ASCII 改名 + typed outputs + 默认接收名。"""

from __future__ import annotations

import yaml

from autobranch.parser.refs import MappingResolver
from autobranch.plugin_system import PluginRegistry, load_builtin_plugins
from scripts.migrate_default_return_param_names import migrate_content


def _registry() -> PluginRegistry:
    reg = PluginRegistry()
    load_builtin_plugins(reg, "autobranch/plugins")
    return reg


def test_migrate_renames_ids_params_and_infers_output_type():
    content = """tree: t
inputs:
  账号: str
outputs:
  - 结果
nodes:
  根:
    type: Root
    body: 节点1
  节点1:
    type: Action
    description: 读取 Param.账号 并写 NewParam.结果:str
root: 根
"""
    out = migrate_content(content, _registry(), MappingResolver())
    data = yaml.safe_load(out)
    assert set(data["nodes"]) == {"n1", "n2"}
    assert data["root"] == "n1"
    assert data["inputs"] == {"input1": "str"}
    assert data["outputs"] == {"output1": "str"}
    desc = data["nodes"]["n2"]["description"]
    assert "Param.input1" in desc and "NewParam.output1" in desc


def test_migrate_fills_default_returns():
    content = """tree: t
nodes:
  n1:
    type: Root
    body: n2
  n2:
    type: FunctionCall
    function: http.request
    args: ["GET", "http://x"]
root: n1
"""
    out = migrate_content(content, _registry(), MappingResolver())
    returns = yaml.safe_load(out)["nodes"]["n2"]["returns"]
    assert returns == {
        "n2_status": "int",
        "n2_body": "str",
        "n2_headers": "object",
    }


def test_migrate_renames_non_ascii_returns():
    content = """tree: t
nodes:
  n1:
    type: Root
    body: n2
  n2:
    type: FunctionCall
    function: browser.get_url
    returns:
      地址: str
root: n1
"""
    out = migrate_content(content, _registry(), MappingResolver())
    data = yaml.safe_load(out)
    assert list(data["nodes"]["n2"]["returns"]) == ["n2_url"]
