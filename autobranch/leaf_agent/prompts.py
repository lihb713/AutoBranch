"""叶子执行提示词模板（M6 spec §5.7.2 提示词设计、design D6 版本化）。

固定模板：系统提示词（角色与行为准则）+ 节点描述 + 语义图正文，模板带版本号
（``PROMPT_VERSION``）。相同输入下渲染结果一致，使 LLM 决策可记录并与后续
运行对比以回归保护（M6 spec 测试策略·提示词回归测试）。

最终回答标记约定（``parse_final_decision`` 解析依据）：
- Action：``结果: 成功`` / ``结果: 失败``
- Condition：``结果: 真`` / ``结果: 假``（确定判断）；``结果: 失败``（无法确定）
"""

from __future__ import annotations

import json
from typing import Literal

from autobranch.parser.models import ActionNode, ConditionNode
from autobranch.schema.types import infer_type

PROMPT_VERSION = "2.1"

_VARIABLE_MECHANISM = """\
变量机制：
1. 行为树维护一个变量表，函数返回值可通过 save_to 参数存入变量
2. 描述中出现 Param.xxx 时，表示引用变量 xxx 中的值
   - 基本类型（str/int/float/bool）：描述中 Param.xxx 会被替换为变量的实际值
   - 对象类型（object/page_ref）：描述中保留 Param.xxx，需配合变量表理解
3. 调用函数时，参数值可填 Param.xxx 来引用变量中存储的对象
4. save_to 参数指定返回值存入哪个变量：
   - 单返回值函数：save_to="变量名"
   - 多返回值函数：save_to={"返回参数名1": "变量名1", "返回参数名2": "变量名2"}
   - 可只指定部分返回值，未指定的返回值不保存
5. save_to 中的变量名必须在 NewParam 声明集内"""

_ACTION_SYSTEM = """\
你是一个自动化执行代理。你的任务是根据「节点描述」，执行对应的操作。

{variable_mechanism}

{schema_hint}

操作规则：
1. 初始语义图已注入用户消息。定位目标元素（ref 形如 [1]）：结合节点描述中的
   文本（"登录按钮"、"Enterprise"）与页面方位标注（如 "页面top-right"）判断哪个 ref 是目标。
2. 语义图始终基于获取时刻的页面状态，页面可能在你操作后变化。**由你自主决定
   是否需要获取最新语义图**：
   - 当要执行的操作可能改变页面布局或关键信息时（如点击、输入、滚动、翻页），
     操作前调用 semantic_graph 获取最新语义图，用最新 ref 定位。
   - 当操作或定位失败（找不到元素、ref 失效、判断依据不足）时，重新调用
     semantic_graph 获取最新语义图后再试，不要用旧 ref 硬试。
   - 其余情况可复用当前语义图，不必每次调用。
3. 若语义图信息不足，可多次调用 semantic_graph(scope, lod) 缩小/放大范围继续定位。
4. 函数调用失败时，阅读返回的错误信息并自行修正（换函数/重新定位/换元素/获取最新语义图），
   引擎不会替你判断。
5. 操作全部完成后，输出最终结果行：`结果: 成功` 或 `结果: 失败`。
6. 若用户消息提示「当前无打开的页面」：说明本动作需要打开/访问一个网址（或引用已保存的
   url 字符串/页签变量）。**直接调用 open(url) 打开新页面**，无需先有当前页面；
   引用已保存的 url 字符串也用 open；引用已保存的页签变量（保存的页面引用）用
   activate 切换。
7. 调用 use_capability 加载能力时，能力名必须**逐字复制**自系统提示中的「可用能力」列表，
   不得臆造或改写名称。
8. 如需直接调用已知 URL 的 API 获取数据（如节点描述中提供了 API 地址）：
   先调用 get_request_headers 分析页面请求的认证信息（如 cookie、CSRF token 等），
   再用 page_request 调用 API（cookie 自动携带，CSRF token 等通过 headers 参数补充）。"""

_CONDITION_SYSTEM = """\
你是一个自动化判断代理。你的任务是根据「节点描述」（条件），判断当前状态是否满足该条件。

{variable_mechanism}

{schema_hint}

判断规则：
1. 初始语义图已注入用户消息。判断页面状态是否满足条件：结合节点描述中的文本
   与页面方位标注（如 "页面bottom"、"第N行"）定位相关元素并判断。
2. 语义图始终基于获取时刻的页面状态，页面可能已变化。**由你自主决定是否需要
   获取最新语义图**：
   - 当判断依赖的页面状态可能已被前序操作改变（如点击后出现的新内容）时，
     先调用 semantic_graph 获取最新语义图再判断。
   - 当判断失败或依据不足（找不到目标元素、状态不明确、无法确定真/假）时，
     重新调用 semantic_graph 获取最新语义图后再判断。
   - 其余情况可复用当前语义图，不必每次调用。
3. 若信息不足，可多次调用 semantic_graph(scope, lod) 缩小/放大范围。
4. 你只负责判断，不要调用 click/type/select 等操作类函数。
5. 得出确定判断后，输出最终结果行：`结果: 真` 或 `结果: 假`；无法确定时输出 `结果: 失败`。"""

_MARKER_PREFIXES = ("结果:", "RESULT:", "FINAL:", "result:")


def build_system_prompt(node: ActionNode | ConditionNode, schema_hint: str) -> str:
    """构建系统提示词（角色 + 行为准则）。

    :param node: 叶子节点（Action/Condition 使用不同角色模板）。
    :param schema_hint: 工具说明文本（如「可用引擎函数: ...」）。
    """
    if isinstance(node, ActionNode):
        template = _ACTION_SYSTEM
    elif isinstance(node, ConditionNode):
        template = _CONDITION_SYSTEM
    else:
        raise TypeError(f"不支持的叶子节点类型: {type(node).__name__}")
    return template.format(
        schema_hint=schema_hint, variable_mechanism=_VARIABLE_MECHANISM
    )


def build_user_message(
    description: str,
    graph_text: str,
    css_hint: str | None = None,
    set_targets: tuple[str, ...] = (),
    set_decls: tuple[tuple[str, str], ...] = (),
    reference: str | None = None,
    variables: list[dict] | None = None,
) -> str:
    """构建用户消息（节点描述 + 当前语义图正文）。

    :param set_targets: 叶子声明的可写变量路径集。
    :param set_decls: ``(path, type)`` 类型标注（TYPE_REGISTRY token）；type=page_ref
      提示用 open 存页签、type=str 提示用 get_url/extract 存文本、其余类型提示
      提取后转换。仅作提示，实际类型由引擎函数保证。
    :param reference: 经验回灌参考段（同行为树同入参历史成功做法，命中才注入；
      明示仅供参考、以当前语义图为准、与当前状态不符时忽略）。
    :param variables: 当前帧变量快照（``[{name, type, value}]``）；渲染变量表供
      LLM 理解对象变量，避免只看到 ``Param.x`` 文本。
    """
    hint = f"\nCSS 提示: {css_hint}" if css_hint else ""
    set_line = ""
    if set_targets:
        type_map = dict(set_decls)
        hints = []
        for target in set_targets:
            type_name = type_map.get(target, "")
            if type_name == "page_ref":
                hints.append(f"{target}（页签：打开页面后调 open 的 save_to 存入）")
            elif type_name == "str":
                hints.append(f"{target}（文本：调 extract 或 get_url 存入）")
            else:
                hints.append(f"{target}（{type_name}：提取并转换后存入）")
        set_line = "\n本动作声明的可写变量: " + "；".join(hints)
        set_line += (
            "\n（写入目标的变量必须在以上声明集内；若描述是“切回/使用已打开页面”"
            "调 activate 而非 open）"
        )
    ref_line = f"\n\n{reference}" if reference else ""
    var_line = _format_variables(variables)
    return (
        f"节点描述: {description}{hint}{set_line}{var_line}{ref_line}"
        f"\n\n当前页面语义图:\n{graph_text}"
    )


def _format_variables(variables: list[dict] | None) -> str:
    """渲染当前变量表（对象显示 repr，长文本截断）。"""
    if not variables:
        return "\n当前变量表: (空)"
    lines = ["\n当前变量表:"]
    for item in variables:
        name = item.get("name") or item.get("path") or "?"
        typ = item.get("type") or infer_type(item.get("value"))
        value = item.get("value")
        text = str(value) if typ not in ("object", "page_ref") else repr(value)
        if len(text) > 200:
            text = text[:200] + "…"
        lines.append(f"  - {name} ({typ}): {text}")
    return "\n".join(lines)


class DecisionError(ValueError):
    """最终回答无法解析为确定的叶子决策。"""


def parse_final_decision(
    text: str,
    node_type: Literal["action", "condition"],
) -> tuple[Literal["success", "failure"], bool | None]:
    """解析 LLM 最终回答为 ``(status, bool_value)``。

    - Action：``结果: 成功`` → ``(success, None)``；``结果: 失败`` → ``(failure, None)``
    - Condition：``结果: 真`` → ``(success, True)``；``结果: 假`` → ``(failure, False)``

    :raises DecisionError: 未识别到确定的结果标记（含 Condition 的
      ``结果: 失败``，表示无法确定，按 LLM 侧失败处理）。
    """
    marker = _find_marker(text)
    if marker is None:
        raise DecisionError(f"最终回答不含可识别的结果标记: {text!r}")
    value = marker.strip().lower()
    if node_type == "action":
        if value in ("成功", "success"):
            return "success", None
        if value in ("失败", "failure"):
            return "failure", None
        raise DecisionError(f"Action 结果标记非法: {marker!r}")
    if value in ("真", "true"):
        return "success", True
    if value in ("假", "false"):
        return "failure", False
    raise DecisionError(f"Condition 未给出确定的真/假判断: {marker!r}")


def _find_marker(text: str) -> str | None:
    """从回答中提取最后一行结果标记值；无标记时尝试解析 JSON 结构化结果。"""
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        for prefix in _MARKER_PREFIXES:
            if line.startswith(prefix):
                return line[len(prefix) :].strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if isinstance(data, dict):
        for key in ("bool_value", "result", "status", "decision"):
            if key in data:
                return str(data[key])
    return None


__all__ = [
    "PROMPT_VERSION",
    "build_system_prompt",
    "build_user_message",
    "parse_final_decision",
    "DecisionError",
]
