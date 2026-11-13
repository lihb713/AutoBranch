"""变量能力插件：把 LLM 推理产出的文本/数据直接写入变量。

`set` 原样返回传入的值，配合引擎的 `save_to` 写入变量；适用于「LLM 从响应中
提取并格式化信息后保存到变量」等没有对应插件函数返回值的场景。
"""

from __future__ import annotations

from autobranch.plugin_system import FunctionResult, PluginBase, engine_function


class VarsPlugin(PluginBase):
    """变量能力：直接写入变量（set）。"""

    name = "vars"
    description = "变量能力：直接写入变量（set）"

    @engine_function(
        name="set",
        description=(
            "直接把值写入变量（原样返回输入值，配合 save_to 存入变量）。"
            "适用于 LLM 自行生成的文本/数据需要保存到变量的场景。"
            "value1/value2/value3 为要写入的值；"
            'save_to 用 {"value1": "变量名1", "value2": "变量名2"} 映射'
        ),
        parameters={
            "type": "object",
            "properties": {
                "value1": {"type": "string", "description": "要写入的值 1"},
                "value2": {"type": "string", "description": "要写入的值 2（可选）"},
                "value3": {"type": "string", "description": "要写入的值 3（可选）"},
            },
            "required": ["value1"],
        },
        returns={"value1": "str", "value2": "str", "value3": "str"},
        output_param="save_to",
    )
    def set(self, value1: str = "", value2: str = "", value3: str = "") -> FunctionResult:
        # 固定返回三个位置，保证 save_to 的返回参数名与索引稳定对应。
        if not (value1 or value2 or value3):
            return FunctionResult.failure("至少需要提供一个值")
        return FunctionResult.success(value1, value2, value3)


plugin = VarsPlugin()

__all__ = ["VarsPlugin", "plugin"]
