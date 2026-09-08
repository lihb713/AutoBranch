"""M3 任务 6.1：集成验收——端到端纯逻辑链路（无浏览器/LLM 依赖）。

覆盖：帧嵌套、传参逐层传递、取子块返回值、配置继承、类型断言失败
传播、页面变量绑定，组合成一条完整场景（登录 → 提取 → 绑定页面）。
"""

from __future__ import annotations

import pytest

from webops.schema import (
    BlockDecl,
    PageRef,
    SchemaError,
    SchemaScopeError,
    SchemaSpace,
    SchemaTypeError,
)


def test_end_to_end_login_export_flow():
    """登录块收到 T 传参 → 转发输入框 → 产出 login_success → T 读取。"""
    space = SchemaSpace(global_config={"timeout": 30})
    t = space.enter_block("T")

    login = space.enter_block(
        "登录",
        BlockDecl(
            block_name="登录",
            inputs={"username": "文本", "password": "文本"},
            outputs={"login_success": "布尔"},
        ),
    )
    ib = space.enter_block("输入框", BlockDecl(block_name="输入框"))
    space.exit_block(ib)

    space.write(t, "$this/登录/username", "alice", "文本")
    space.write(t, "$this/登录/password", "p@ss", "文本")
    space.write(login, "$this/输入框/值", space.read(login, "$this/username"), "文本")
    assert space.read(ib, "$this/值") == "alice"

    space.write(login, "$this/login_success", True, "布尔")
    space.exit_block(login)

    assert space.read(t, "$this/登录/login_success") is True
    assert space.resolve_config(t, "timeout") == 30


def test_end_to_end_config_and_page_binding():
    """配置覆盖 + 页面变量绑定 → 操作作用于当前页面变量所指页。"""
    space = SchemaSpace(global_config={"timeout": 30})
    t = space.enter_block("T")
    space.set_config(t, "timeout", 120, "整数")
    login = space.enter_block("登录")
    assert space.resolve_config(login, "timeout") == 120

    login_page = PageRef("p1", "https://example.com/login")
    space.write(t, "$this/登录页", login_page, "页面引用")
    bound = space.current_page(t)
    assert bound == login_page
    assert bound.page_id == "p1"


def test_end_to_end_assertion_failure_propagates():
    """类型断言失败沿调用链传播，M7 捕获即终止。"""
    space = SchemaSpace()
    t = space.enter_block("T")
    login = space.enter_block("登录")
    with pytest.raises(SchemaTypeError):
        space.write(login, "$this/amount", "不是数字", "金额")
    with pytest.raises(SchemaError):
        space.write(t, "$this/登录/amount", "也不是数字", "金额")


def test_end_to_end_grandchild_invisible():
    """严格作用域贯穿链路：T 不可见孙子帧，越权即抛错。"""
    space = SchemaSpace()
    t = space.enter_block("T")
    space.enter_block("登录")
    space.enter_block("输入框")
    with pytest.raises(SchemaScopeError):
        space.read(t, "$this/登录/输入框/值")
