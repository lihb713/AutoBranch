"""M3 schema 命名空间：类型契约（契约 §5.3.5）。

``SUPPORTED_TYPES`` 集中登记支持的类型与对应的校验函数。写入时声明
类型并即时校验，读取/提取时二次强校验；校验失败触发
``SchemaTypeError``（断言失败语义），由上层（M7）捕获并终止流程。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime

from webops.schema.errors import SchemaTypeError
from webops.schema.models import PageRef, Value


def _is_money(value: Value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.strip())
            return True
        except ValueError:
            return False
    return False


def _is_order_no(value: Value) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not any(ch.isspace() for ch in value)
    )


def _is_url(value: Value) -> bool:
    return (
        isinstance(value, str)
        and (value.startswith("http://") or value.startswith("https://"))
        and len(value) > 7
    )


def _is_date(value: Value) -> bool:
    if isinstance(value, (date, datetime)):
        return True
    if isinstance(value, str):
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return True
        except ValueError:
            return False
    return False


def _is_text(value: Value) -> bool:
    return isinstance(value, str)


def _is_page_ref(value: Value) -> bool:
    return isinstance(value, PageRef)


def _is_bool(value: Value) -> bool:
    return isinstance(value, bool)


def _is_int(value: Value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


SUPPORTED_TYPES: dict[str, Callable[[Value], bool]] = {
    "金额": _is_money,
    "订单号": _is_order_no,
    "URL": _is_url,
    "日期": _is_date,
    "文本": _is_text,
    "页面引用": _is_page_ref,
    "布尔": _is_bool,
    "整数": _is_int,
    "数字": _is_number,
}


def validate_type_name(type_name: str) -> None:
    """校验类型名在登记表内，否则断言失败。"""
    if type_name not in SUPPORTED_TYPES:
        raise SchemaTypeError(
            f"不支持的变量类型: {type_name!r}（支持: {sorted(SUPPORTED_TYPES)}）"
        )


def check_type(type_name: str, value: Value) -> None:
    """强校验值是否符合声明类型，不匹配触发断言失败（契约 §5.3.5）。"""
    validate_type_name(type_name)
    if not SUPPORTED_TYPES[type_name](value):
        raise SchemaTypeError(f"类型断言失败: 值 {value!r} 不符合类型 {type_name!r}")


def infer_type(value: Value) -> str:
    """按值推断类型（用于配置参数缺省声明类型）。"""
    if isinstance(value, bool):
        return "布尔"
    if isinstance(value, int):
        return "整数"
    if isinstance(value, float):
        return "数字"
    if isinstance(value, PageRef):
        return "页面引用"
    return "文本"
