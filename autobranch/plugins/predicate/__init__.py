"""常用谓词插件：只返回单个 bool，供条件表达式使用。

所有函数均为确定性、无副作用、用户可见；不能写变量。
"""

from __future__ import annotations

import re
from typing import Any

from autobranch.plugin_system import FunctionResult, PluginBase, engine_function


def _params(required: tuple[str, ...], **props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(required)}


def _failure(message: str) -> FunctionResult:
    return FunctionResult.failure(message, code="PREDICATE_ERROR")


def _compare(a: Any, b: Any, op: str) -> FunctionResult:
    handlers = {
        "eq": lambda: a == b,
        "ne": lambda: a != b,
        "gt": lambda: a > b,
        "ge": lambda: a >= b,
        "lt": lambda: a < b,
        "le": lambda: a <= b,
    }
    handler = handlers.get(op)
    if handler is None:
        return _failure(f"不支持的比较操作: {op}")
    try:
        return FunctionResult.success(bool(handler()))
    except TypeError as exc:
        return _failure(f"无法比较 {a!r} 与 {b!r}: {exc}")


class PredicatePlugin(PluginBase):
    """常用布尔谓词。"""

    name = "predicate"
    description = "条件表达式常用谓词：比较、字符串、空值、集合、长度"

    @engine_function(
        name="eq",
        description="a 是否等于 b",
        parameters=_params(
            ("a", "b"),
            a={"description": "值 a"},
            b={"description": "值 b"},
        ),
        returns={"result": "bool"},
    )
    def eq(self, a: Any, b: Any) -> FunctionResult:
        return _compare(a, b, "eq")

    @engine_function(
        name="ne",
        description="a 是否不等于 b",
        parameters=_params(
            ("a", "b"),
            a={"description": "值 a"},
            b={"description": "值 b"},
        ),
        returns={"result": "bool"},
    )
    def ne(self, a: Any, b: Any) -> FunctionResult:
        return _compare(a, b, "ne")

    @engine_function(
        name="gt",
        description="a 是否大于 b",
        parameters=_params(
            ("a", "b"),
            a={"description": "值 a"},
            b={"description": "值 b"},
        ),
        returns={"result": "bool"},
    )
    def gt(self, a: Any, b: Any) -> FunctionResult:
        return _compare(a, b, "gt")

    @engine_function(
        name="ge",
        description="a 是否大于等于 b",
        parameters=_params(
            ("a", "b"),
            a={"description": "值 a"},
            b={"description": "值 b"},
        ),
        returns={"result": "bool"},
    )
    def ge(self, a: Any, b: Any) -> FunctionResult:
        return _compare(a, b, "ge")

    @engine_function(
        name="lt",
        description="a 是否小于 b",
        parameters=_params(
            ("a", "b"),
            a={"description": "值 a"},
            b={"description": "值 b"},
        ),
        returns={"result": "bool"},
    )
    def lt(self, a: Any, b: Any) -> FunctionResult:
        return _compare(a, b, "lt")

    @engine_function(
        name="le",
        description="a 是否小于等于 b",
        parameters=_params(
            ("a", "b"),
            a={"description": "值 a"},
            b={"description": "值 b"},
        ),
        returns={"result": "bool"},
    )
    def le(self, a: Any, b: Any) -> FunctionResult:
        return _compare(a, b, "le")

    @engine_function(
        name="between",
        description="value 是否在 [low, high] 闭区间内",
        parameters=_params(
            ("value", "low", "high"),
            value={"description": "待判断值"},
            low={"description": "下界"},
            high={"description": "上界"},
        ),
        returns={"result": "bool"},
    )
    def between(self, value: Any, low: Any, high: Any) -> FunctionResult:
        try:
            return FunctionResult.success(bool(low <= value <= high))
        except TypeError as exc:
            return _failure(f"无法进行区间比较: {exc}")

    @engine_function(
        name="contains",
        description="字符串是否包含子串，或列表是否包含元素",
        parameters=_params(
            ("value", "needle"),
            value={"description": "字符串或列表"},
            needle={"description": "子串或元素"},
            ignore_case={"type": "boolean", "description": "字符串比较忽略大小写"},
        ),
        returns={"result": "bool"},
    )
    def contains(self, value: Any, needle: Any, ignore_case: bool = False) -> FunctionResult:
        if isinstance(value, str):
            left, right = value, str(needle)
            if ignore_case:
                left, right = left.lower(), right.lower()
            return FunctionResult.success(right in left)
        if isinstance(value, (list, tuple)):
            return FunctionResult.success(any(item == needle for item in value))
        return _failure("contains 的 value 必须是字符串或列表")

    @engine_function(
        name="not_contains",
        description="字符串/列表是否不包含目标",
        parameters=_params(
            ("value", "needle"),
            value={"description": "字符串或列表"},
            needle={"description": "子串或元素"},
            ignore_case={"type": "boolean", "description": "字符串比较忽略大小写"},
        ),
        returns={"result": "bool"},
    )
    def not_contains(
        self, value: Any, needle: Any, ignore_case: bool = False
    ) -> FunctionResult:
        result = self.contains(value, needle, ignore_case)
        if not result.ok:
            return result
        return FunctionResult.success(not bool(result.value))

    @engine_function(
        name="starts_with",
        description="字符串是否以指定前缀开头",
        parameters=_params(
            ("value", "prefix"),
            value={"type": "string", "description": "原字符串"},
            prefix={"type": "string", "description": "前缀"},
            ignore_case={"type": "boolean", "description": "忽略大小写"},
        ),
        returns={"result": "bool"},
    )
    def starts_with(self, value: str, prefix: str, ignore_case: bool = False) -> bool:
        return value.lower().startswith(prefix.lower()) if ignore_case else value.startswith(prefix)

    @engine_function(
        name="ends_with",
        description="字符串是否以指定后缀结尾",
        parameters=_params(
            ("value", "suffix"),
            value={"type": "string", "description": "原字符串"},
            suffix={"type": "string", "description": "后缀"},
            ignore_case={"type": "boolean", "description": "忽略大小写"},
        ),
        returns={"result": "bool"},
    )
    def ends_with(self, value: str, suffix: str, ignore_case: bool = False) -> bool:
        return value.lower().endswith(suffix.lower()) if ignore_case else value.endswith(suffix)

    @engine_function(
        name="matches",
        description="字符串是否匹配正则表达式（搜索，不要求整串匹配）",
        parameters=_params(
            ("value", "pattern"),
            value={"type": "string", "description": "原字符串"},
            pattern={"type": "string", "description": "正则表达式"},
            ignore_case={"type": "boolean", "description": "忽略大小写"},
        ),
        returns={"result": "bool"},
    )
    def matches(self, value: str, pattern: str, ignore_case: bool = False) -> FunctionResult:
        flags = re.IGNORECASE if ignore_case else 0
        try:
            return FunctionResult.success(re.search(pattern, value, flags) is not None)
        except re.error as exc:
            return _failure(f"正则错误: {exc}")

    @engine_function(
        name="matches_full",
        description="字符串是否完整匹配正则表达式",
        parameters=_params(
            ("value", "pattern"),
            value={"type": "string", "description": "原字符串"},
            pattern={"type": "string", "description": "正则表达式"},
            ignore_case={"type": "boolean", "description": "忽略大小写"},
        ),
        returns={"result": "bool"},
    )
    def matches_full(
        self, value: str, pattern: str, ignore_case: bool = False
    ) -> FunctionResult:
        flags = re.IGNORECASE if ignore_case else 0
        try:
            return FunctionResult.success(re.fullmatch(pattern, value, flags) is not None)
        except re.error as exc:
            return _failure(f"正则错误: {exc}")

    @engine_function(
        name="equals_ignore_case",
        description="两个字符串忽略大小写是否相等",
        parameters=_params(
            ("a", "b"),
            a={"type": "string", "description": "字符串 a"},
            b={"type": "string", "description": "字符串 b"},
        ),
        returns={"result": "bool"},
    )
    def equals_ignore_case(self, a: str, b: str) -> bool:
        return str(a).lower() == str(b).lower()

    @engine_function(
        name="is_empty",
        description="是否为 None、空字符串、空列表或空字典",
        parameters=_params(("value",), value={"description": "待判断值"}),
        returns={"result": "bool"},
    )
    def is_empty(self, value: Any) -> bool:
        return value is None or value == "" or value == [] or value == {}

    @engine_function(
        name="is_not_empty",
        description="是否不为空",
        parameters=_params(("value",), value={"description": "待判断值"}),
        returns={"result": "bool"},
    )
    def is_not_empty(self, value: Any) -> bool:
        return not self.is_empty(value)

    @engine_function(
        name="is_null",
        description="是否为 None（null）",
        parameters=_params(("value",), value={"description": "待判断值"}),
        returns={"result": "bool"},
    )
    def is_null(self, value: Any) -> bool:
        return value is None

    @engine_function(
        name="is_not_null",
        description="是否不为 None（null）",
        parameters=_params(("value",), value={"description": "待判断值"}),
        returns={"result": "bool"},
    )
    def is_not_null(self, value: Any) -> bool:
        return value is not None

    @engine_function(
        name="has_key",
        description="字典是否包含指定键",
        parameters=_params(
            ("data", "key"),
            data={"type": "object", "description": "字典"},
            key={"type": "string", "description": "键"},
        ),
        returns={"result": "bool"},
    )
    def has_key(self, data: dict, key: str) -> FunctionResult:
        if not isinstance(data, dict):
            return _failure("has_key 的 data 必须是字典")
        return FunctionResult.success(key in data)

    @engine_function(
        name="has_value",
        description="字典是否包含指定值",
        parameters=_params(
            ("data", "value"),
            data={"type": "object", "description": "字典"},
            value={"description": "值"},
        ),
        returns={"result": "bool"},
    )
    def has_value(self, data: dict, value: Any) -> FunctionResult:
        if not isinstance(data, dict):
            return _failure("has_value 的 data 必须是字典")
        return FunctionResult.success(any(item == value for item in data.values()))

    @engine_function(
        name="value_in",
        description="值是否在列表中",
        parameters=_params(
            ("value", "values"),
            value={"description": "待查找值"},
            values={"type": "array", "items": {}, "description": "候选列表"},
        ),
        returns={"result": "bool"},
    )
    def value_in(self, value: Any, values: list[Any]) -> FunctionResult:
        if not isinstance(values, (list, tuple)):
            return _failure("value_in 的 values 必须是列表")
        return FunctionResult.success(any(item == value for item in values))

    @engine_function(
        name="value_not_in",
        description="值是否不在列表中",
        parameters=_params(
            ("value", "values"),
            value={"description": "待查找值"},
            values={"type": "array", "items": {}, "description": "候选列表"},
        ),
        returns={"result": "bool"},
    )
    def value_not_in(self, value: Any, values: list[Any]) -> FunctionResult:
        result = self.value_in(value, values)
        if not result.ok:
            return result
        return FunctionResult.success(not bool(result.value))

    def _length_compare(self, value: Any, n: int, op: str) -> FunctionResult:
        try:
            size = len(value)
        except TypeError:
            return _failure("length 谓词的 value 必须支持长度")
        return _compare(size, n, op)

    @engine_function(
        name="length_eq",
        description="长度是否等于 n",
        parameters=_params(
            ("value", "n"),
            value={"description": "字符串/列表/字典"},
            n={"type": "integer", "description": "长度"},
        ),
        returns={"result": "bool"},
    )
    def length_eq(self, value: Any, n: int) -> FunctionResult:
        return self._length_compare(value, n, "eq")

    @engine_function(
        name="length_ge",
        description="长度是否大于等于 n",
        parameters=_params(
            ("value", "n"),
            value={"description": "字符串/列表/字典"},
            n={"type": "integer", "description": "长度"},
        ),
        returns={"result": "bool"},
    )
    def length_ge(self, value: Any, n: int) -> FunctionResult:
        return self._length_compare(value, n, "ge")

    @engine_function(
        name="length_gt",
        description="长度是否大于 n",
        parameters=_params(
            ("value", "n"),
            value={"description": "字符串/列表/字典"},
            n={"type": "integer", "description": "长度"},
        ),
        returns={"result": "bool"},
    )
    def length_gt(self, value: Any, n: int) -> FunctionResult:
        return self._length_compare(value, n, "gt")

    @engine_function(
        name="length_le",
        description="长度是否小于等于 n",
        parameters=_params(
            ("value", "n"),
            value={"description": "字符串/列表/字典"},
            n={"type": "integer", "description": "长度"},
        ),
        returns={"result": "bool"},
    )
    def length_le(self, value: Any, n: int) -> FunctionResult:
        return self._length_compare(value, n, "le")

    @engine_function(
        name="length_lt",
        description="长度是否小于 n",
        parameters=_params(
            ("value", "n"),
            value={"description": "字符串/列表/字典"},
            n={"type": "integer", "description": "长度"},
        ),
        returns={"result": "bool"},
    )
    def length_lt(self, value: Any, n: int) -> FunctionResult:
        return self._length_compare(value, n, "lt")


plugin = PredicatePlugin()

__all__ = ["PredicatePlugin", "plugin"]
