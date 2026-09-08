"""M3 任务 4.x：类型契约（写入/提取强校验）与统一断言失败异常。"""

from __future__ import annotations

from datetime import date

import pytest

from webops.schema import PageRef, SchemaError, SchemaSpace, SchemaTypeError


@pytest.fixture
def space() -> SchemaSpace:
    return SchemaSpace()


def test_valid_values_write_ok(space):
    """4.1 各类型合法值写入成功。"""
    t = space.enter_block("T")
    space.write(t, "$this/amount", 98.00, "金额")
    space.write(t, "$this/amount2", "98.00", "金额")
    space.write(t, "$this/order", "ORD-001", "订单号")
    space.write(t, "$this/url", "https://example.com/x", "URL")
    space.write(t, "$this/date", "2024-05-01", "日期")
    space.write(t, "$this/date2", date(2024, 5, 1), "日期")
    space.write(t, "$this/text", "任意文本", "文本")
    space.write(t, "$this/ref", PageRef("p1"), "页面引用")
    space.write(t, "$this/bool", True, "布尔")
    space.write(t, "$this/int", 5, "整数")
    space.write(t, "$this/num", 5.5, "数字")


@pytest.mark.parametrize(
    "value,type_name,desc",
    [
        ("abc", "金额", "文本写金额"),
        ("¥98.00", "金额", "含货币符号写金额"),
        (True, "金额", "布尔写金额"),
        (1, "布尔", "整数写布尔"),
        ("ftp://x", "URL", "非 http 协议"),
        ("not a url", "URL", "无协议"),
        ("有 空格", "订单号", "订单号含空格"),
        ("2024-13-45", "日期", "非法日期"),
        ("123", "未知类型", "未登记类型"),
    ],
)
def test_invalid_write_rejected(space, value, type_name, desc):
    """4.2 非法类型值写入触发断言失败并终止。"""
    t = space.enter_block("T")
    with pytest.raises(SchemaTypeError, match="断言失败|不支持的变量类型"):
        space.write(t, "$this/x", value, type_name)


def test_type_error_is_schema_error(space):
    """4.3 断言失败异常可被 M7 统一捕获（基类 SchemaError）。"""
    t = space.enter_block("T")
    caught: list[str] = []
    try:
        space.write(t, "$this/x", "abc", "金额")
    except SchemaError as err:
        assert isinstance(err, SchemaTypeError)
        caught.append("propagated")
    assert caught == ["propagated"]


def test_extract_time_strong_validation(space):
    """4.2 提取/读取时强校验：存储被绕开污染 → 读取断言失败。"""
    t = space.enter_block("T")
    login = space.enter_block("登录")
    space.exit_block(login)
    space.write(t, "$this/登录/amount", 100, "金额")
    # 模拟上层绕开 write 直接污染存储（declared 仍声明为金额）
    login.storage["amount"] = "not-a-number"
    with pytest.raises(SchemaTypeError, match="断言失败"):
        space.read(t, "$this/登录/amount")


def test_extract_url_violation(space):
    """4.2 URL 变量存储值异常 → 提取时断言失败。"""
    t = space.enter_block("T")
    space.write(t, "$this/url", "https://ok.example", "URL")
    t.storage["url"] = "ftp://bad.example"
    with pytest.raises(SchemaTypeError):
        space.read(t, "$this/url")


def test_typed_write_then_read_roundtrip(space):
    """4.1/4.2 合法值写入后可正确读取。"""
    t = space.enter_block("T")
    space.write(t, "$this/order", "ORD-001", "订单号")
    assert space.read(t, "$this/order") == "ORD-001"
