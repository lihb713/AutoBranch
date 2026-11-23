"""计算插件（M7 插件集）：确定性数值运算 / 排序 / 比较（纯函数）。

函数只返回值、不写变量；同输入同输出、无外部副作用。
"""

from __future__ import annotations

from typing import Any

from autobranch.plugin_system import FunctionResult, PluginBase, engine_function


def _params(required: tuple[str, ...], **props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(required)}


class ComputePlugin(PluginBase):
    """计算能力：数值运算、排序、比较。"""

    name = "compute"
    description = "计算能力：四则/取模/幂/开方/绝对值/取整/聚合/排序/比较"

    @engine_function(
        name="multiply",
        description="两个数相乘（确定性纯函数）",
        parameters=_params(
            ("a", "b"),
            a={"type": "number", "description": "被乘数"},
            b={"type": "number", "description": "乘数"},
        ),
        returns={"result": "float"},
    )
    def multiply(self, a: float, b: float) -> float:
        return float(a * b)

    @engine_function(
        name="sort",
        description="对数值列表排序（默认升序，desc 可降序）",
        parameters=_params(
            ("data",),
            data={"type": "array", "items": {}, "description": "待排序数值列表"},
            desc={"type": "boolean", "description": "是否降序（默认升序）"},
        ),
        returns={"result": "array"},
    )
    def sort(self, data: list[Any], desc: bool = False) -> list[Any]:
        return sorted(data, reverse=bool(desc))

    @engine_function(
        name="compare",
        description="比较两个数值，op 支持 gt/ge/lt/le/eq/ne（默认 gt）",
        parameters=_params(
            ("a", "b"),
            a={"type": "number", "description": "值 a"},
            b={"type": "number", "description": "值 b"},
            op={
                "type": "string",
                "description": "比较操作（默认 gt）",
                "enum": ["gt", "ge", "lt", "le", "eq", "ne"],
            },
        ),
        returns={"result": "bool"},
    )
    def compare(self, a: float, b: float, op: str = "gt") -> FunctionResult:
        handlers = {
            "gt": lambda: a > b,
            "ge": lambda: a >= b,
            "lt": lambda: a < b,
            "le": lambda: a <= b,
            "eq": lambda: a == b,
            "ne": lambda: a != b,
        }
        handler = handlers.get(str(op))
        if handler is None:
            return FunctionResult.failure(f"不支持的比较操作: {op}")
        return FunctionResult.success(bool(handler()))

    @engine_function(
        name="add",
        description="两个数相加（确定性纯函数）",
        parameters=_params(
            ("a", "b"),
            a={"type": "number", "description": "加数 a"},
            b={"type": "number", "description": "加数 b"},
        ),
        returns={"result": "float"},
    )
    def add(self, a: float, b: float) -> float:
        return float(a + b)

    @engine_function(
        name="sum",
        description="对数值列表求和（确定性纯函数）",
        parameters=_params(
            ("values",),
            values={"type": "array", "items": {"type": "number"}, "description": "数值列表"},
        ),
        returns={"total": "float"},
    )
    def sum(self, values: list[float]) -> float:
        return float(sum(values))



    @engine_function(
        name="subtract",
        description="两个数相减（a - b）",
        parameters=_params(
            ("a", "b"),
            a={"type": "number", "description": "被减数"},
            b={"type": "number", "description": "减数"},
        ),
        returns={"result": "float"},
    )
    def subtract(self, a: float, b: float) -> float:
        return float(a - b)

    @engine_function(
        name="divide",
        description="两个数相除（a / b，除数为 0 返回失败）",
        parameters=_params(
            ("a", "b"),
            a={"type": "number", "description": "被除数"},
            b={"type": "number", "description": "除数"},
        ),
        returns={"result": "float"},
    )
    def divide(self, a: float, b: float) -> FunctionResult:
        if b == 0:
            return FunctionResult.failure("除数不能为 0")
        return FunctionResult.success(a / b)

    @engine_function(
        name="floor_divide",
        description="整除（a // b，除数为 0 返回失败）",
        parameters=_params(
            ("a", "b"),
            a={"type": "number", "description": "被除数"},
            b={"type": "number", "description": "除数"},
        ),
        returns={"result": "int"},
    )
    def floor_divide(self, a: float, b: float) -> FunctionResult:
        if b == 0:
            return FunctionResult.failure("除数不能为 0")
        return FunctionResult.success(int(a // b))

    @engine_function(
        name="modulo",
        description="取余（a % b，除数为 0 返回失败）",
        parameters=_params(
            ("a", "b"),
            a={"type": "number", "description": "被除数"},
            b={"type": "number", "description": "除数"},
        ),
        returns={"result": "float"},
    )
    def modulo(self, a: float, b: float) -> FunctionResult:
        if b == 0:
            return FunctionResult.failure("除数不能为 0")
        return FunctionResult.success(float(a % b))

    @engine_function(
        name="power",
        description="幂运算（a 的 b 次方）",
        parameters=_params(
            ("a", "b"),
            a={"type": "number", "description": "底数"},
            b={"type": "number", "description": "指数"},
        ),
        returns={"result": "float"},
    )
    def power(self, a: float, b: float) -> float:
        return float(a**b)

    @engine_function(
        name="sqrt",
        description="平方根（负数返回失败）",
        parameters=_params(("value",), value={"type": "number", "description": "数值"}),
        returns={"result": "float"},
    )
    def sqrt(self, value: float) -> FunctionResult:
        if value < 0:
            return FunctionResult.failure("负数不能开平方")
        return FunctionResult.success(float(value**0.5))

    @engine_function(
        name="abs_value",
        description="绝对值",
        parameters=_params(("value",), value={"type": "number", "description": "数值"}),
        returns={"result": "float"},
    )
    def abs_value(self, value: float) -> float:
        return float(abs(value))

    @engine_function(
        name="negate",
        description="取相反数",
        parameters=_params(("value",), value={"type": "number", "description": "数值"}),
        returns={"result": "float"},
    )
    def negate(self, value: float) -> float:
        return float(-value)

    @engine_function(
        name="round_value",
        description="四舍五入到指定小数位（digits 默认 0）",
        parameters=_params(
            ("value",),
            value={"type": "number", "description": "数值"},
            digits={"type": "integer", "description": "小数位数（默认 0）"},
        ),
        returns={"result": "float"},
    )
    def round_value(self, value: float, digits: int = 0) -> float:
        return float(round(value, int(digits)))

    @engine_function(
        name="min_values",
        description="返回数值列表最小值（空列表返回失败）",
        parameters=_params(
            ("values",),
            values={"type": "array", "items": {"type": "number"}, "description": "数值列表"},
        ),
        returns={"result": "float"},
    )
    def min_values(self, values: list[float]) -> FunctionResult:
        if not values:
            return FunctionResult.failure("列表不能为空")
        return FunctionResult.success(float(min(values)))

    @engine_function(
        name="max_values",
        description="返回数值列表最大值（空列表返回失败）",
        parameters=_params(
            ("values",),
            values={"type": "array", "items": {"type": "number"}, "description": "数值列表"},
        ),
        returns={"result": "float"},
    )
    def max_values(self, values: list[float]) -> FunctionResult:
        if not values:
            return FunctionResult.failure("列表不能为空")
        return FunctionResult.success(float(max(values)))

    @engine_function(
        name="average",
        description="返回数值列表平均值（空列表返回失败）",
        parameters=_params(
            ("values",),
            values={"type": "array", "items": {"type": "number"}, "description": "数值列表"},
        ),
        returns={"result": "float"},
    )
    def average(self, values: list[float]) -> FunctionResult:
        if not values:
            return FunctionResult.failure("列表不能为空")
        return FunctionResult.success(float(sum(values) / len(values)))

    @engine_function(
        name="clamp",
        description="把数值限制在 [low, high] 区间",
        parameters=_params(
            ("value", "low", "high"),
            value={"type": "number", "description": "数值"},
            low={"type": "number", "description": "下限"},
            high={"type": "number", "description": "上限"},
        ),
        returns={"result": "float"},
    )
    def clamp(self, value: float, low: float, high: float) -> FunctionResult:
        if low > high:
            return FunctionResult.failure("下限不能大于上限")
        return FunctionResult.success(float(min(max(value, low), high)))

    @engine_function(
        name="percentage",
        description="计算 part 占 total 的百分比（total 为 0 返回失败）",
        parameters=_params(
            ("part", "total"),
            part={"type": "number", "description": "部分值"},
            total={"type": "number", "description": "总量"},
        ),
        returns={"result": "float"},
    )
    def percentage(self, part: float, total: float) -> FunctionResult:
        if total == 0:
            return FunctionResult.failure("总量不能为 0")
        return FunctionResult.success(float(part / total * 100))

    @engine_function(
        name="increment",
        description="数值增加 step（默认 1）",
        parameters=_params(
            ("value",),
            value={"type": "number", "description": "数值"},
            step={"type": "number", "description": "增量（默认 1）"},
        ),
        returns={"result": "float"},
    )
    def increment(self, value: float, step: float = 1) -> float:
        return float(value + step)

    @engine_function(
        name="decrement",
        description="数值减少 step（默认 1）",
        parameters=_params(
            ("value",),
            value={"type": "number", "description": "数值"},
            step={"type": "number", "description": "减量（默认 1）"},
        ),
        returns={"result": "float"},
    )
    def decrement(self, value: float, step: float = 1) -> float:
        return float(value - step)

plugin = ComputePlugin()


__all__ = ["ComputePlugin", "plugin"]
