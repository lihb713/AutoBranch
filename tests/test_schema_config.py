"""M3 任务 3.x：配置参数继承（自身 → 最近祖先 → 全局默认）与业务变量不向上查找。"""

from __future__ import annotations

import pytest

from webops.schema import FrameDecl, SchemaSpace


@pytest.fixture
def space() -> SchemaSpace:
    return SchemaSpace(global_config={"timeout": 30})


def test_own_config_wins(space):
    """3.1 块自身配置优先（块覆盖）。"""
    t = space.enter_frame("T")
    login = space.enter_frame(
        "登录", FrameDecl(name="登录", config={"timeout": 60})
    )
    assert space.resolve_config(login, "timeout") == 60
    assert space.resolve_config(t, "timeout") == 30


def test_nearest_ancestor(space):
    """3.1 向上找最近祖先。"""
    space.enter_frame("T")
    mid = space.enter_frame(
        "中间", FrameDecl(name="中间", config={"retry": 5})
    )
    leaf = space.enter_frame("叶子", FrameDecl(name="叶子"))
    assert space.resolve_config(leaf, "retry") == 5
    assert space.resolve_config(mid, "retry") == 5
    space.exit_frame(leaf)
    space.exit_frame(mid)


def test_global_default_fallback(space):
    """3.1 全局默认兜底（三级继承末端）。"""
    space.enter_frame("T")
    space.enter_frame("登录", FrameDecl(name="登录"))
    ib = space.enter_frame("输入框", FrameDecl(name="输入框"))
    assert space.resolve_config(ib, "timeout") == 30


def test_global_default_injected_to_root(space):
    """3.2 全局默认初始化注入根级帧，各子帧继承解析正确。"""
    assert space.resolve_config(space.root, "timeout") == 30
    t = space.enter_frame("T")
    assert space.resolve_config(t, "timeout") == 30
    login = space.enter_frame("登录", FrameDecl(name="登录"))
    assert space.resolve_config(login, "timeout") == 30


def test_override_only_affects_block_and_descendants(space):
    """3.1/3.2 块覆盖值只在当前块及以下生效。"""
    t = space.enter_frame("T")
    space.enter_frame("登录")
    space.exit_frame()
    space.set_config(t, "timeout", 90, "int")
    assert space.resolve_config(t, "timeout") == 90
    # 登录是 T 的直接子，T 覆盖后登录应继承 90（向上找最近祖先）
    login = space.enter_frame("登录")
    assert space.resolve_config(login, "timeout") == 90


def test_business_variable_not_looked_up(space):
    """3.3 业务变量不向上查找：读自身未定义返回空值，不取祖先同名值。"""
    t = space.enter_frame("T")
    space.write(t, "$this/username", "alice", "str")
    login = space.enter_frame("登录")
    assert space.read(login, "$this/username") is None
    # 而 T 自己读得到
    assert space.read(t, "$this/username") == "alice"


def test_set_config_type_validated(space):
    """3.x set_config 触发类型校验。"""
    t = space.enter_frame("T")
    space.set_config(t, "retry", 3, "int")
    assert space.resolve_config(t, "retry") == 3


def test_config_missing_returns_none():
    """3.1 全局默认与祖先均无该配置 → 返回 None。"""
    space = SchemaSpace()
    t = space.enter_frame("T")
    assert space.resolve_config(t, "不存在的配置") is None
