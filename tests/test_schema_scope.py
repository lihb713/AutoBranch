"""M3 任务 2.x：帧模型、严格作用域矩阵、传参逐层传递、取子块返回值。"""

from __future__ import annotations

import pytest

from webops.schema import FrameDecl, SchemaScopeError, SchemaSpace


@pytest.fixture
def space() -> SchemaSpace:
    return SchemaSpace(global_config={"timeout": 30})


def _build_tree(space: SchemaSpace):
    """T → (登录 → 输入框) 与 T → 导出。"""
    t = space.enter_frame("T")
    login = space.enter_frame("登录", FrameDecl(name="登录"))
    ib = space.enter_frame("输入框", FrameDecl(name="输入框"))
    space.exit_frame(ib)
    space.exit_frame(login)
    export = space.enter_frame("导出", FrameDecl(name="导出"))
    space.exit_frame(export)
    return t, login, ib, export


def test_frame_isolation_same_name():
    """2.1 两次引用同名块，同名变量互不冲突。"""
    space = SchemaSpace()
    space.enter_frame("T")
    a1 = space.enter_frame("登录")
    space.write(a1, "$this/username", "alice", "str")
    assert space.read(a1, "$this/username") == "alice"
    space.exit_frame(a1)

    a2 = space.enter_frame("登录")
    space.write(a2, "$this/username", "bob", "str")
    assert space.read(a2, "$this/username") == "bob"
    assert space.read(a1, "$this/username") == "alice"


def test_nested_frame_paths():
    """2.1 嵌套调用形成层级帧路径 T/ → T/登录/ → T/登录/输入框/。"""
    space = SchemaSpace()
    t = space.enter_frame("T")
    login = space.enter_frame("登录")
    ib = space.enter_frame("输入框")
    assert t.path == "T/"
    assert login.path == "T/登录/"
    assert ib.path == "T/登录/输入框/"


def test_write_own_and_read_own(space):
    """2.2 写/读自己的 schema 合法。"""
    t, *_ = _build_tree(space)
    space.write(t, "$this/amount", 100.0, "float")
    assert space.read(t, "$this/amount") == 100.0
    assert space.read(t, "T/amount") == 100.0


def test_write_direct_child_rejected(space):
    """2.2 父块写直接子帧已废除（跨帧传参经 ref args，帧路径仅单段）。"""
    t, login, *_ = _build_tree(space)
    with pytest.raises(SchemaScopeError):
        space.write(t, "$this/登录/username", "alice", "str")


@pytest.mark.parametrize(
    "actor,path,desc",
    [
        ("login", "$this/T/amount", "子块写祖先帧"),
        ("login", "T/amount", "子块以块名形式写祖先帧"),
        ("login", "$this/导出/amount", "子块写兄弟帧"),
        ("login", "导出/amount", "子块以块名形式写兄弟帧"),
        ("t", "$this/登录/输入框/值", "写孙子帧"),
        ("login", "$this/输入框/孙子/x", "写孙子帧（隔一层）"),
    ],
)
def test_write_scope_matrix_rejected(space, actor, path, desc):
    """2.2 越权写：祖先/兄弟/孙子帧全部被拒绝。"""
    t, login, _, _ = _build_tree(space)
    frame = t if actor == "t" else login
    with pytest.raises(SchemaScopeError, match="越权"):
        space.write(frame, path, "x", "str")


@pytest.mark.parametrize(
    "actor,path,desc",
    [
        ("login", "$this/T/amount", "子块读祖先帧"),
        ("login", "T/amount", "子块以块名形式读祖先帧"),
        ("login", "$this/导出/amount", "子块读兄弟帧"),
        ("t", "$this/登录/输入框/值", "读孙子帧"),
        ("t", "$this/输入框/x", "读非直接子帧（语义歧义）"),
    ],
)
def test_read_scope_matrix_rejected(space, actor, path, desc):
    """2.2 越权读：祖先/兄弟/孙子帧全部被拒绝。"""
    t, login, _, _ = _build_tree(space)
    frame = t if actor == "t" else login
    with pytest.raises(SchemaScopeError, match="越权"):
        space.read(frame, path)


def test_param_passing_layer_by_layer(space):
    """2.3 传参逐层传递：T → 登录 → 输入框（各帧局部单段写入/读取）。"""
    t, login, ib, _ = _build_tree(space)
    space.write(t, "this/username", "alice", "str")
    space.write(login, "this/username", space.read(t, "this/username"), "str")
    space.write(login, "this/值", space.read(login, "this/username"), "str")
    space.write(ib, "this/值", space.read(login, "this/值"), "str")
    assert space.read(ib, "this/值") == "alice"


def test_grandchild_invisible_to_top(space):
    """2.3 T 无法直接写/读孙级路径（逐层转发强制）。"""
    t, _, _, _ = _build_tree(space)
    with pytest.raises(SchemaScopeError):
        space.write(t, "$this/登录/输入框/值", "x", "str")
    with pytest.raises(SchemaScopeError):
        space.read(t, "$this/登录/输入框/值")


def test_read_direct_child_result_rejected(space):
    """2.3 跨帧读直接子帧返回值已废除（经 ref returns 传递，帧路径仅单段）。"""
    t, _, _, export = _build_tree(space)
    space.write(export, "$this/result", "done", "str")
    with pytest.raises(SchemaScopeError):
        space.read(t, "$this/导出/result")


def test_read_undefined_variable_returns_none(space):
    """2.2 读取未定义变量返回空值，不产生越权错误。"""
    t, *_ = _build_tree(space)
    assert space.read(t, "$this/undefined") is None
