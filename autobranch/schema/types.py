"""M3 schema 命名空间：类型契约（契约 §5.3.5，收敛版）。

``TYPE_REGISTRY`` 把 DSL token 映射到**真实 Python 类型**，校验统一
``isinstance``；``coerce`` 把用户输入的文本转成目标真实类型。类型即
存储类型——声明 ``int`` 的变量存的就是 Python ``int``，声明 ``array`` /
``object`` 的变量分别存 Python ``list`` / ``dict``。

基本类型：str/int/float/bool/array/object。``generics`` 表示不确定类型
（类似泛型，任意值），``page_ref`` 是唯一自定义类型（无 cast，只能由
引擎 open() 产生）。校验失败触发 ``SchemaTypeError``（断言失败语义），
由 M7 捕获。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from autobranch.schema.errors import SchemaTypeError
from autobranch.schema.models import PageRef, Value


@dataclass(frozen=True)
class TypeSpec:
    """类型注册项：DSL token → 真实 Python 类型 + 可选 cast。

    :param token: DSL 引用名（str/int/float/bool/array/object/generics/page_ref）。
    :param py_type: 真实 Python 类型（isinstance 校验目标）。
    :param cast: 用户文本 → 该类型的转换；None = 不可由文本产生
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


def _to_object(value: Value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise SchemaTypeError(f"无法转成 object（需要 JSON 对象）: {value!r}") from exc
        if isinstance(parsed, dict):
            return parsed
    raise SchemaTypeError(f"无法转成 object（需要 JSON 对象）: {value!r}")


def _to_array(value: Value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise SchemaTypeError(f"无法转成 array（需要 JSON 数组）: {value!r}") from exc
        if isinstance(parsed, list):
            return parsed
    raise SchemaTypeError(f"无法转成 array（需要 JSON 数组）: {value!r}")


def _identity(value: Value) -> Value:
    return value


TYPE_REGISTRY: dict[str, TypeSpec] = {
    "str": TypeSpec("str", str, lambda v: str(v)),
    "int": TypeSpec("int", int, _to_int),
    "float": TypeSpec("float", float, _to_float),
    "bool": TypeSpec("bool", bool, _to_bool),
    "array": TypeSpec("array", list, _to_array),
    "object": TypeSpec("object", dict, _to_object),
    "generics": TypeSpec("generics", object, _identity),
    "page_ref": TypeSpec("page_ref", PageRef, None),
}


def validate_type_name(token: str) -> None:
    if token not in TYPE_REGISTRY:
        raise SchemaTypeError(
            f"不支持的变量类型: {token!r}（支持: {sorted(TYPE_REGISTRY)}）"
        )


def check_type(token: str, value: Value) -> None:
    """强校验值是否是该 token 对应 Python 类型的实例（契约 §5.3.5）。

    ``generics`` 为不确定类型：不校验具体类型（任意值）。
    """
    spec = TYPE_REGISTRY.get(token)
    if spec is None:
        raise SchemaTypeError(f"不支持的变量类型: {token!r}")
    if token == "generics":
        return
    if token == "int" and isinstance(value, bool):
        raise SchemaTypeError(f"类型断言失败: 值 {value!r} 不符合类型 'int'（排除布尔）")
    if not isinstance(value, spec.py_type):
        raise SchemaTypeError(f"类型断言失败: 值 {value!r} 不符合类型 {token!r}")


def coerce(token: str, raw: Value) -> Value:
    """按 token 把用户文本转成真实存储类型。

    ``array`` / ``object`` 接受 JSON 数组/对象文本；已经是 ``list`` / ``dict``
    的值原样保留（函数返回值等运行时值不重复转换）。``generics`` 原样返回。
    ``cast is None``（如 page_ref）拒绝文本转换——只能由引擎函数产生。
    """
    if token == "generics":
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


def is_fully_basic(value: Value) -> bool:
    """值是否完全由基本标量/容器构成（不含 generics/page_ref 等自定义值）。

    list/dict 递归检查全部元素；None 视为可文本化的基本值；其他对象
    （PageRef、插件对象等）返回 False。
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(is_fully_basic(item) for item in value)
    if isinstance(value, dict):
        return all(
            is_fully_basic(key) and is_fully_basic(item)
            for key, item in value.items()
        )
    return False


def infer_type(value: Value) -> str:
    """按 Python 值类型推断 token（用于缺省声明类型）。"""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, PageRef):
        return "page_ref"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "generics"
