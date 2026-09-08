"""M3 任务 5.x：页面变量机制（PageRef 存储/多页面变量/传参/绑定）。"""

from __future__ import annotations

import pytest

from webops.schema import PageRef, SchemaSpace


@pytest.fixture
def space() -> SchemaSpace:
    return SchemaSpace()


def test_open_result_written_as_page_ref(space):
    """5.1 open 返回值写入页面引用变量，可被后续读取。"""
    t = space.enter_block("T")
    page = PageRef("p1", "https://example.com/login")
    space.write(t, "$this/登录页", page, "页面引用")
    assert space.read(t, "$this/登录页") == page


def test_multiple_page_vars_in_one_frame(space):
    """5.2 一个帧可持有多个页面变量且互不覆盖。"""
    t = space.enter_block("T")
    login_page = PageRef("p1", "https://example.com/login")
    order_page = PageRef("p2", "https://example.com/orders")
    space.write(t, "$this/登录页", login_page, "页面引用")
    space.write(t, "$this/订单页", order_page, "页面引用")
    assert space.read(t, "$this/登录页") == login_page
    assert space.read(t, "$this/订单页") == order_page
    refs = dict(space.page_refs(t))
    assert refs == {"登录页": login_page, "订单页": order_page}


def test_page_ref_passed_as_ordinary_param(space):
    """5.3 页面变量按普通参数传参（父块写子帧）。"""
    t = space.enter_block("T")
    login = space.enter_block("登录")
    space.exit_block(login)
    login_page = PageRef("p1", "https://example.com/login")
    space.write(t, "$this/登录页", login_page, "页面引用")
    space.write(t, "$this/登录/页面", login_page, "页面引用")
    assert space.read(login, "$this/页面") == login_page


def test_current_page_resolves_latest(space):
    """5.4 当前页面变量解析：返回最近写入的页面引用。"""
    t = space.enter_block("T")
    login_page = PageRef("p1")
    order_page = PageRef("p2")
    space.write(t, "$this/登录页", login_page, "页面引用")
    space.write(t, "$this/订单页", order_page, "页面引用")
    assert space.current_page(t) == order_page
    # 再次写入登录页 → 最近写入变为登录页
    space.write(t, "$this/登录页", login_page, "页面引用")
    assert space.current_page(t) == login_page


def test_current_page_none_without_page_var(space):
    """5.4 无页面变量时返回 None。"""
    t = space.enter_block("T")
    space.write(t, "$this/amount", 100, "金额")
    assert space.current_page(t) is None
    leaf = space.enter_block("叶子")
    assert space.current_page(leaf) is None


def test_current_page_ignores_ordinary_writes(space):
    """5.4 普通变量写入不影响当前页面变量解析。"""
    t = space.enter_block("T")
    page = PageRef("p1")
    space.write(t, "$this/登录页", page, "页面引用")
    space.write(t, "$this/amount", 100, "金额")
    assert space.current_page(t) == page
