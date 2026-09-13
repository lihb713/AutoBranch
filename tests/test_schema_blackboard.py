"""M3 变量引用（裸变量名）与 blackboard 快照测试。

覆盖：裸变量名读写（兼容 `this/` 前缀）、`snapshot_variables` 以「文档名/变量名」
平铺导出（无层级）。
"""

from __future__ import annotations

import pytest

from webops.schema import PageRef, SchemaSpace
from webops.schema.errors import SchemaScopeError


def _space() -> SchemaSpace:
    return SchemaSpace(global_config={"timeout": 30})


def test_bare_name_write_read():
    """裸变量名读写（get/set 均针对当前文档帧）。"""
    sp = _space()
    root = sp.enter_frame("主流程")
    sp.write(root, "amount", 98.0, "float")
    assert sp.read(root, "amount") == 98.0


def test_this_path_still_compatible():
    """兼容旧式 `this/param` / `$this/param` 路径读写。"""
    sp = _space()
    root = sp.enter_frame("主流程")
    sp.write(root, "this/amount", 98.0, "float")
    assert sp.read(root, "this/amount") == 98.0
    assert sp.read(root, "$this/amount") == 98.0
    assert sp.read(root, "amount") == 98.0


def test_frames_isolated_bare_names():
    """各文档帧变量隔离：子帧裸名变量与父帧互不冲突。"""
    sp = _space()
    root = sp.enter_frame("主流程")
    child = sp.enter_frame("登录")
    sp.write(root, "username", "父", "str")
    sp.write(child, "username", "子", "str")
    assert sp.read(root, "username") == "父"
    assert sp.read(child, "username") == "子"
    sp.exit_frame()


def test_cross_frame_path_rejected():
    """跨帧多段路径（祖先/兄弟/孙子）越权被拒。"""
    sp = _space()
    sp.enter_frame("主流程")
    child = sp.enter_frame("登录")
    with pytest.raises(SchemaScopeError):
        sp.read(child, "主流程/x")
    with pytest.raises(SchemaScopeError):
        sp.read(child, "登录/子块/x")
    sp.exit_frame()


def test_snapshot_variables_flat():
    """snapshot_variables 导出各帧变量为「文档名/变量名」（无层级）。"""
    sp = _space()
    root = sp.enter_frame("主流程")
    sp.write(root, "amount", 98.0, "float")
    child = sp.enter_frame("登录")
    sp.write(child, "username", "admin", "str")
    sp.exit_frame()

    snap = sp.snapshot_variables(root)
    paths = {item["path"]: item for item in snap}
    assert paths["主流程/amount"]["value"] == 98.0
    assert paths["主流程/amount"]["type"] == "float"
    assert paths["登录/username"]["value"] == "admin"
    assert paths["登录/username"]["type"] == "str"
    assert "this/" not in " ".join(paths)


def test_snapshot_variables_contains_page_ref():
    sp = _space()
    root = sp.enter_frame("主流程")
    sp.write(root, "登录页", PageRef(page_id="1", url="http://x"), "page_ref")
    snap = sp.snapshot_variables(root)
    paths = {item["path"]: item for item in snap}
    assert paths["主流程/登录页"]["type"] == "page_ref"
    assert paths["主流程/登录页"]["value"].page_id == "1"


def test_snapshot_variables_uses_current_frame():
    sp = _space()
    root = sp.enter_frame("主流程")
    sp.write(root, "a", "1", "str")
    child = sp.enter_frame("登录")
    sp.write(child, "b", "2", "str")
    # 当前激活帧是登录子帧 → 仅展示登录帧变量
    snap = sp.snapshot_variables()
    paths = {item["path"] for item in snap}
    assert "登录/b" in paths
    assert "主流程/a" not in paths
    sp.exit_frame()
