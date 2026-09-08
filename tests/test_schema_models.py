"""M3 任务 1.x：Value 类型、SchemaFrame 数据结构、路径工具、SUPPORTED_TYPES。"""

from __future__ import annotations

import pytest

from webops.schema import (
    SUPPORTED_TYPES,
    BlockDecl,
    PageRef,
    SchemaFrame,
    SchemaPathError,
    SchemaScopeError,
    SchemaTypeError,
    Value,
    check_type,
    infer_type,
    validate_type_name,
)
from webops.schema.path import resolve_target, split_segments
from webops.schema.types import _is_bool, _is_date, _is_money, _is_order_no, _is_url


def make_frame(block_name: str = "T") -> SchemaFrame:
    return SchemaFrame(
        id=1,
        block_name=block_name,
        parent=None,
        path_segments=(block_name,),
    )


def test_value_alias_scalars():
    """1.1 Value 覆盖标量类型与页面引用。"""
    for v in ("文本", 1, 1.5, True, None):
        assert isinstance(v, Value) or v is None
    assert isinstance(PageRef("p1"), Value)


def test_frame_is_pure_memory():
    """1.1 SchemaFrame 为纯内存结构：字段齐全、无 I/O。"""
    frame = make_frame()
    assert frame.block_name == "T"
    assert frame.parent is None
    assert frame.path_segments == ("T",)
    assert frame.path == "T/"
    assert frame.storage == {}
    assert frame.declared == {}
    assert frame.config == {}
    assert frame.children == {}


def test_frame_children_and_path():
    """1.1 直接子帧挂接与层级路径。"""
    t = make_frame("T")
    login = SchemaFrame(
        id=2, block_name="登录", parent=t, path_segments=t.path_segments + ("登录",)
    )
    t.children["登录"] = login
    assert login.parent is t
    assert login.path == "T/登录/"


def test_block_decl_defaults():
    """1.1 BlockDecl 默认字段为空 dict。"""
    decl = BlockDecl(block_name="登录")
    assert decl.inputs == {}
    assert decl.outputs == {}
    assert decl.config == {}
    assert decl.config_types == {}


def test_split_segments_valid():
    """1.2 合法路径按 / 分层。"""
    assert split_segments("$this/amount") == ("$this", "amount")
    assert split_segments("T/登录/username") == ("T", "登录", "username")


def test_split_segments_empty_rejected():
    """1.2 空路径与空分段被拒绝。"""
    with pytest.raises(SchemaPathError):
        split_segments("")
    with pytest.raises(SchemaPathError):
        split_segments("$this//amount")
    with pytest.raises(SchemaPathError):
        split_segments("$this/")


def test_split_segments_rejects_var_with_slash():
    """1.2 含 / 的变量名在解析时被拒绝（多段 → 越权/非法）。"""
    frame = make_frame("T")
    with pytest.raises(SchemaScopeError):
        resolve_target(frame, "$this/订单/号")


def test_supported_types_enumerable():
    """1.3 类型登记表可枚举核心类型。"""
    for name in ["金额", "订单号", "URL", "日期", "文本", "页面引用", "布尔"]:
        assert name in SUPPORTED_TYPES
    assert "整数" in SUPPORTED_TYPES
    assert "数字" in SUPPORTED_TYPES


def test_supported_types_checkers():
    """1.3 各类型校验函数行为。"""
    assert _is_money(98.00)
    assert _is_money(98)
    assert _is_money("98.00")
    assert not _is_money("abc")
    assert not _is_money("¥98.00")
    assert not _is_money(True)

    assert _is_order_no("ORD-001")
    assert not _is_order_no("有 空格")
    assert not _is_order_no("")

    assert _is_url("https://example.com/x")
    assert not _is_url("ftp://example.com")
    assert not _is_url("example.com")

    assert _is_date("2024-05-01")
    assert not _is_date("2024-13-45")

    assert _is_bool(True)
    assert not _is_bool(1)


def test_validate_type_name():
    """1.3 未登记类型名 → SchemaTypeError。"""
    validate_type_name("金额")
    with pytest.raises(SchemaTypeError):
        validate_type_name("未知类型")


def test_check_type_ok():
    check_type("金额", 100)
    check_type("页面引用", PageRef("p1"))


def test_infer_type():
    """1.3 配置参数缺省类型按值推断。"""
    assert infer_type(True) == "布尔"
    assert infer_type(5) == "整数"
    assert infer_type(5.5) == "数字"
    assert infer_type("x") == "文本"
    assert infer_type(PageRef("p1")) == "页面引用"
