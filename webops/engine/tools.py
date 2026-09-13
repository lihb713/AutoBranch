"""工具函数注册表（契约 §5.8.1、M5 spec §5.1）。

``ENGINE_TOOLS`` 以工具 schema（M0 ``ToolSpec``）形式暴露给 LLM 的引擎
函数集，与 ``EngineFunctions`` 同名方法配对：注册表是纯声明，执行实现是
引擎内部细节（design D1）。函数集可扩展——追加一个 ``ToolSpec`` 并实现
同名方法即注册即用，无需改动既有函数（契约 §5.8.1）。
"""

from __future__ import annotations

from webops.llm import ToolSpec


def _prop_string(description: str, enum: list[str] | None = None) -> dict:
    schema: dict = {"type": "string", "description": description}
    if enum is not None:
        schema["enum"] = list(enum)
    return schema


def _object_params(required: tuple[str, ...], **props: dict) -> dict:
    """构造 JSON Schema 对象参数：properties + required。"""
    return {"type": "object", "properties": props, "required": list(required)}


_REF_DESC = "语义图元素引用（如 [1]，来自最近一次 semantic_graph）"

ENGINE_TOOLS: list[ToolSpec] = [
    # ---- 页面函数 ----
    ToolSpec(
        name="open",
        description=(
            "打开 URL 新建页签并设为当前活动页。仅当动作描述含 [[set:page_ref:xxx]] "
            "声明要保存页签时才把 save_to 填为对应变量名（形如 this/页面A）；否则省略 "
            "save_to（只打开页面，不保存变量）。描述含 [[set:str:xxx]] 存 URL 字符串时用 "
            "get_url，不用本函数。"
        ),
        parameters=_object_params(
            ("url",),
            url=_prop_string("要打开的 URL，如 https://example.com/login"),
            save_to=_prop_string(
                "（可选，仅当描述含 [[set:page_ref:...]] 声明时）页签引用存入的变量，"
                "形如 this/页面A"
            ),
        ),
    ),
    ToolSpec(
        name="activate",
        description=(
            "把已打开的页签设为当前活动页（切换焦点，不新建）。"
            "当描述是“回到/切到/使用已打开的 X 页”时调用，page_var 填该页签变量名。"
        ),
        parameters=_object_params(
            ("page_var",),
            page_var=_prop_string("已存页签的变量名，形如 this/页面A（必须是页面引用变量）"),
        ),
    ),
    ToolSpec(
        name="get_url",
        description=(
            "取当前活动页的 URL 字符串并存入变量（文本类型）。"
            "当动作描述含 [[set:str:xxx]] 存 URL 字符串时用本函数。"
        ),
        parameters=_object_params(
            ("save_to",),
            save_to=_prop_string("URL 字符串存入的变量，形如 this/url"),
        ),
    ),
    # ---- 操作类函数（作用于当前页面变量指向的页，§5.10） ----
    ToolSpec(
        name="click",
        description="点击语义图元素（作用于当前页面变量指向的页）",
        parameters=_object_params(("ref",), ref=_prop_string(_REF_DESC)),
    ),
    ToolSpec(
        name="type",
        description="向输入元素输入文本（替换现有值，作用于当前页面）",
        parameters=_object_params(
            ("ref", "text"),
            ref=_prop_string(_REF_DESC),
            text=_prop_string("要输入的文本"),
        ),
    ),
    ToolSpec(
        name="select",
        description="下拉选择选项（优先按选项文本匹配，其次按 value 匹配）",
        parameters=_object_params(
            ("ref", "option"),
            ref=_prop_string(_REF_DESC),
            option=_prop_string("要选择的选项文本或 value"),
        ),
    ),
    ToolSpec(
        name="check",
        description="勾选勾选类控件（checkbox/radio，作用于当前页面）",
        parameters=_object_params(("ref",), ref=_prop_string(_REF_DESC)),
    ),
    ToolSpec(
        name="uncheck",
        description="取消勾选勾选类控件（checkbox/radio，作用于当前页面）",
        parameters=_object_params(("ref",), ref=_prop_string(_REF_DESC)),
    ),
    ToolSpec(
        name="scroll",
        description="滚动当前页面（up/down/left/right/top/bottom）",
        parameters=_object_params(
            ("direction",),
            direction=_prop_string(
                "滚动方向", ["up", "down", "left", "right", "top", "bottom"]
            ),
        ),
    ),
    ToolSpec(
        name="wait",
        description=(
            "等待条件满足（条件语法：selector: <CSS>/text: <文本>/url: <子串>，默认 selector）"
        ),
        parameters=_object_params(
            ("condition",),
            condition=_prop_string("等待条件，如 selector: #login-btn"),
        ),
    ),
    # ---- 文件函数 ----
    ToolSpec(
        name="download",
        description="触发下载（点击下载链接/按钮）并保存文件",
        parameters=_object_params(("ref",), ref=_prop_string(_REF_DESC)),
    ),
    ToolSpec(
        name="upload",
        description="上传文件到文件选择控件（作用于当前页面）",
        parameters=_object_params(
            ("ref", "path"),
            ref=_prop_string(_REF_DESC),
            path=_prop_string("本地文件路径"),
        ),
    ),
    # ---- 语义图函数 ----
    ToolSpec(
        name="semantic_graph",
        description="获取当前页面变量的语义图（每次完整生成、无缓存，生成后旧 ref 全部失效）",
        parameters=_object_params(
            ("scope", "lod"),
            scope=_prop_string("范围：full 全页，或区域 id（如 F1/T1）"),
            lod={
                "type": "integer",
                "minimum": 0,
                "maximum": 3,
                "description": "LOD 级别 0~3（信息量递增）",
            },
        ),
    ),
    # ---- HTTP 函数 ----
    ToolSpec(
        name="clear_requests",
        description="清理页面请求记录（形态 A：此后只读取新发生的页面请求）",
        parameters=_object_params(()),
    ),
    ToolSpec(
        name="get_response",
        description="读取页面已发生且与模式匹配的请求响应（形态 A，无匹配返回失败）",
        parameters=_object_params(
            ("method", "url_pattern"),
            method=_prop_string("HTTP 方法，如 GET/POST"),
            url_pattern=_prop_string("URL 模式（* 为通配符，不含 * 时按子串匹配）"),
        ),
    ),
    ToolSpec(
        name="http_request",
        description=(
            "发起独立 HTTP 请求（形态 B，不经页面；认证信息经 headers 显式提供，"
            "不携带页面会话）"
        ),
        parameters=_object_params(
            ("method", "url"),
            method=_prop_string("HTTP 方法，如 GET/POST"),
            url=_prop_string("请求 URL"),
            headers={"type": "object", "description": "请求头（含认证 token/cookie 等）"},
            body=_prop_string("请求体（字符串）"),
        ),
    ),
    # ---- 提取函数 ----
    ToolSpec(
        name="extract",
        description="提取语义图元素的值并写入 schema 变量（写入前经 M3 类型校验）",
        parameters=_object_params(
            ("ref", "target"),
            ref=_prop_string(_REF_DESC),
            target=_prop_string("目标变量路径，如 this/订单号"),
        ),
    ),
]


def tool_names() -> list[str]:
    """注册表内全部函数名。"""
    return [tool.name for tool in ENGINE_TOOLS]


__all__ = ["ENGINE_TOOLS", "tool_names"]
