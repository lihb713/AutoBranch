"""计算插件（M7 插件集）：确定性数值运算 / 排序 / 比较（纯函数）。

函数只返回值、不写变量；同输入同输出、无外部副作用。
"""

from __future__ import annotations

from typing import Any

from autobranch.plugin_system import PluginBase, engine_function


def _params(required: tuple[str, ...], **props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(required)}


class ComputePlugin(PluginBase):
    """计算能力：数值运算、排序、比较。"""

    name = "compute"
    description = "计算能力：数值运算（multiply）、排序（sort）、比较（compare）"

    @engine_function(
        name="multiply",
        description="两个数相乘（确定性纯函数）",
        parameters=_params(
            ("a", "b"),
            a={"type": "number", "description": "被乘数"},
            b={"type": "number", "description": "乘数"},
        ),
        returns=("result",),
    )
    def multiply(self, a: float, b: float) -> float:
        return a * b

    @engine_function(
        name="sort",
        description="对数值列表排序（默认升序，desc 可降序）",
        parameters=_params(
            ("data",),
            data={"type": "array", "items": {}, "description": "待排序数值列表"},
            desc={"type": "boolean", "description": "是否降序（默认升序）"},
        ),
        returns=("result",),
    )
    def sort(self, data: list[Any], desc: bool = False) -> list[Any]:
        return sorted(data, reverse=bool(desc))

    @engine_function(
        name="compare",
        description="比较两个值，返回 a > b 的布尔结果",
        parameters=_params(
            ("a", "b"),
            a={"type": "number", "description": "值 a"},
            b={"type": "number", "description": "值 b"},
        ),
        returns=("result",),
    )
    def compare(self, a: float, b: float) -> bool:
        return a > b

    @engine_function(
        name="add",
        description="两个数相加（确定性纯函数）",
        parameters=_params(
            ("a", "b"),
            a={"type": "number", "description": "加数 a"},
            b={"type": "number", "description": "加数 b"},
        ),
        returns=("result",),
    )
    def add(self, a: float, b: float) -> float:
        return a + b

    @engine_function(
        name="sum",
        description="对数值列表求和（确定性纯函数）",
        parameters=_params(
            ("values",),
            values={"type": "array", "items": {"type": "number"}, "description": "数值列表"},
        ),
        returns=("total",),
    )
    def sum(self, values: list[float]) -> float:
        return float(sum(values))


plugin = ComputePlugin()


__all__ = ["ComputePlugin", "plugin"]
