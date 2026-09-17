"""迁移脚本单元测试：裸函数名 → 全名改写（保留文档格式）。"""

from __future__ import annotations

from autobranch.plugin_system import PluginRegistry
from autobranch.plugins.compute import ComputePlugin
from scripts.migrate_function_names import bare_to_full, migrate_content


def _mapping() -> dict[str, str]:
    reg = PluginRegistry()
    reg.register(ComputePlugin())
    return bare_to_full(reg)


def test_bare_to_full_mapping():
    mapping = _mapping()
    assert mapping["add"] == "compute.add"
    assert mapping["multiply"] == "compute.multiply"
    assert "sum" in mapping


def test_migrate_bare_to_full():
    content = "    function: add\n    args: [a, b]\n"
    new, changes = migrate_content(content, _mapping())
    assert "function: compute.add" in new
    assert changes == [("", "add", "compute.add")]


def test_migrate_preserves_quotes_and_indent():
    content = "  function: 'add'\n"
    new, changes = migrate_content(content, _mapping())
    assert new == "  function: 'compute.add'\n"
    assert changes == [("", "add", "compute.add")]


def test_already_full_name_unchanged():
    content = "    function: compute.add\n"
    new, changes = migrate_content(content, _mapping())
    assert new == content
    assert changes == []


def test_unknown_name_reported_and_kept():
    content = "    function: nope\n"
    new, changes = migrate_content(content, _mapping())
    assert new == content
    assert changes == [("", "nope", None)]


def test_null_function_unchanged():
    content = "    function: null\n"
    new, changes = migrate_content(content, _mapping())
    assert new == content
    assert changes == []


def test_migrate_flow_style_inline():
    content = (
        '  n3: {type: FunctionCall, function: add, args: ["2", "3"], returns: {结果: int}}\n'
    )
    new, changes = migrate_content(content, _mapping())
    assert "function: compute.add" in new
    assert changes == [("", "add", "compute.add")]


def test_migrate_full_document():
    content = """tree: 求和
nodes:
  r:
    type: Root
    body: n1
  n1:
    type: FunctionCall
    function: add
    args: [a, b]
    returns:
      结果: int
  n2:
    type: FunctionCall
    function: multiply
    args: [a, b]
    returns:
      结果: int
root: r
"""
    new, changes = migrate_content(content, _mapping())
    assert "function: compute.add" in new
    assert "function: compute.multiply" in new
    assert changes == [
        ("", "add", "compute.add"),
        ("", "multiply", "compute.multiply"),
    ]
    # 其余结构行保持不变
    assert "type: FunctionCall" in new
    assert "type: Root" in new
