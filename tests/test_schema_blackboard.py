"""M3 变量引用新语法与 blackboard 快照测试。

覆盖：``this/``（无 $）路径读写、``snapshot_variables`` 快照导出。
"""

from __future__ import annotations

import pytest

from webops.schema import PageRef, SchemaSpace
from webops.schema.errors import SchemaScopeError


def _space() -> SchemaSpace:
    return SchemaSpace(global_config={"timeout": 30})


def test_this_path_write_read():
    """`this/param`（无 $）路径读写与 `$this/param` 等价。"""
    sp = _space()
    root = sp.enter_block("主流程")
    sp.write(root, "this/amount", 98.0, "float")
    assert sp.read(root, "this/amount") == 98.0
    # 旧 $this 仍内部兼容
    assert sp.read(root, "$this/amount") == 98.0


def test_this_child_path_write_read():
    """`this/直接子块/param` 传参与取返回值。"""
    sp = _space()
    root = sp.enter_block("主流程")
    child = sp.enter_block("登录")
    sp.write(root, "this/登录/username", "admin", "str")
    assert sp.read(child, "this/username") == "admin"
    assert sp.read(root, "this/登录/username") == "admin"
    sp.exit_block()


def test_this_scope_violation_read():
    """`this` 引用祖先/兄弟/孙子帧越权被拒。"""
    sp = _space()
    root = sp.enter_block("主流程")
    child = sp.enter_block("登录")
    # 子块尝试读孙块（未建）→ 越权
    with pytest.raises(SchemaScopeError):
        sp.read(child, "this/子块/x")
    sp.exit_block()
    # 根块尝试读兄弟级（不存在）→ 越权
    with pytest.raises(SchemaScopeError):
        sp.read(root, "this/不存在/块/x")


def test_snapshot_variables_flat():
    """snapshot_variables 导出当前帧变量（含子帧）。"""
    sp = _space()
    root = sp.enter_block("主流程")
    sp.write(root, "this/amount", 98.0, "float")
    child = sp.enter_block("登录")
    sp.write(child, "this/username", "admin", "str")
    sp.exit_block()

    snap = sp.snapshot_variables(root)
    paths = {item["path"]: item for item in snap}
    assert paths["this/amount"]["value"] == 98.0
    assert paths["this/amount"]["type"] == "float"
    assert paths["this/登录/username"]["value"] == "admin"
    assert paths["this/登录/username"]["type"] == "str"


def test_snapshot_variables_contains_page_ref():
    sp = _space()
    root = sp.enter_block("主流程")
    sp.write(root, "this/登录页", PageRef(page_id="1", url="http://x"), "page_ref")
    snap = sp.snapshot_variables(root)
    paths = {item["path"]: item for item in snap}
    assert paths["this/登录页"]["type"] == "page_ref"
    assert paths["this/登录页"]["value"].page_id == "1"


def test_snapshot_variables_uses_current_frame():
    sp = _space()
    root = sp.enter_block("主流程")
    sp.write(root, "this/a", "1", "str")
    child = sp.enter_block("登录")
    sp.write(child, "this/b", "2", "str")
    # 当前激活帧是登录子块
    snap = sp.snapshot_variables()
    paths = {item["path"] for item in snap}
    assert "this/b" in paths
    assert "this/a" not in paths  # 父帧不可见
    sp.exit_block()
