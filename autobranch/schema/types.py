"""M3 schema 命名空间：类型契约（契约 §5.3.5，收敛版）。

``TYPE_REGISTRY`` 把 DSL token 映射到**真实 Python 类型**，校验统一
``isinstance``；``coerce`` 把网页提取的 str 转成目标真实类型。类型即
存储类型——声明 ``int`` 的变量存的就是 Python ``int``。

自定义类型扩展 = 注册表加一行（token + Python 类 + 可选 cast）。当前
唯一自定义类型是 ``page_ref``（页签引用，无 cast，只能由引擎 open()
产生）。校验失败触发 ``SchemaTypeError``（断言失败语义），由 M7 捕获。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from autobranch.schema.errors import SchemaTypeError
from autobranch.schema.models import PageRef, Value


@dataclass(frozen=True)
class TypeSpec:
    """类型注册项：DSL token → 真实 Python 类型 + 可选 cast。

    :param token: DSL 引用名（str/int/float/bool/page_ref）。
    :param py_type: 真实 Python 类型（isinstance 校验目标）。
    :param cast: 网页 str → 该类型的转换；None = 不可由文本产生
      （如 page_ref，只能由引擎函数生成）。
    """

    token: str
    py_type: type
    cast: Callable[[Value], Value] | None = None


def _to_int(value: Value) -> int:
    if isinstance(value, bool):
        raise SchemaTypeError(f"不能把布尔转成整数: {value!r}")
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise SchemaTypeError(f"无法转成 int: {value!r}") from exc


def _to_float(value: Value) -> float:
    if isinstance(value, bool):
        raise SchemaTypeError(f"不能把布尔转成浮点: {value!r}")
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise SchemaTypeError(f"无法转成 float: {value!r}") from exc


def _to_bool(value: Value) -> bool:
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off", ""):
        return False
    raise SchemaTypeError(f"无法转成 bool: {value!r}")


TYPE_REGISTRY: dict[str, TypeSpec] = {
    "str": TypeSpec("str", str, lambda v: str(v)),
    "int": TypeSpec("int", int, _to_int),
    "float": TypeSpec("float", float, _to_float),
    "bool": TypeSpec("bool", bool, _to_bool),
    "page_ref": TypeSpec("page_ref", PageRef, None),
    "object": TypeSpec("object", object, None),
}


def validate_type_name(token: str) -> None:
    if token not in TYPE_REGISTRY:
        raise SchemaTypeError(
            f"不支持的变量类型: {token!r}（支持: {sorted(TYPE_REGISTRY)}）"
        )


def check_type(token: str, value: Value) -> None:
    """强校验值是否是该 token 对应 Python 类型的实例（契约 §5.3.5）。

    ``object`` 为泛型对象类型：不校验具体类型（任意对象值）。
    """
    spec = TYPE_REGISTRY.get(token)
    if spec is None:
        raise SchemaTypeError(f"不支持的变量类型: {token!r}")
    if token == "object":
        return
    if token == "int" and isinstance(value, bool):
        raise SchemaTypeError(f"类型断言失败: 值 {value!r} 不符合类型 'int'（排除布尔）")
    if not isinstance(value, spec.py_type):
        raise SchemaTypeError(f"类型断言失败: 值 {value!r} 不符合类型 {token!r}")


def coerce(token: str, raw: Value) -> Value:
    """按 token 把值转成真实存储类型（set 标注驱动；网页值→Python 类型）。

    ``object`` 泛型对象类型：任意值原样存储（不转换、不校验）。
    ``cast is None``（如 page_ref）拒绝文本转换——只能由引擎函数产生。
    """
    if token == "object":
        return raw
    spec = TYPE_REGISTRY.get(token)
    if spec is None:
        raise SchemaTypeError(f"不支持的变量类型: {token!r}")
    if isinstance(raw, spec.py_type) and token != "int":
        return raw
    if spec.cast is None:
        raise SchemaTypeError(
            f"类型 {token!r} 不能由值 {raw!r} 转换，只能由引擎函数产生"
        )
    if token == "int" and isinstance(raw, spec.py_type) and isinstance(raw, bool):
        raise SchemaTypeError(f"不能把布尔存成 int: {raw!r}")
    return spec.cast(raw)


def infer_type(value: Value) -> str:
    """按 Python 值类型推断 token（用于缺省声明类型）。"""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, PageRef):
        return "page_ref"
    return "str"
