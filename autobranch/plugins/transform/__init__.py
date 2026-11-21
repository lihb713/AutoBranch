"""数据提取与变换插件（纯函数，无外部副作用）。

覆盖列表/字典路径读取、索引/键读取、字符串切分/拼接/搜索/替换、
类型转换、JSON、正则与通用比较。函数只返回值，不写变量。
"""

from __future__ import annotations

import json
import re
from typing import Any

from autobranch.plugin_system import FunctionResult, PluginBase, engine_function


def _params(required_names: tuple[str, ...], **props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(required_names)}


def _failure(message: str) -> FunctionResult:
    return FunctionResult.failure(message, code="TRANSFORM_ERROR")


def _path_tokens(path: str) -> list[str]:
    text = (path or "").strip()
    if not text:
        return []
    text = text.replace("[", ".").replace("]", "")
    return [token for token in text.split(".") if token != ""]


def _read_path(data: Any, path: str) -> Any:
    current = data
    for token in _path_tokens(path):
        if isinstance(current, dict):
            current = current[token]
        elif isinstance(current, (list, tuple)):
            current = current[int(token)]
        else:
            raise TypeError(f"路径 {path!r} 在 {type(current).__name__} 处无法继续")
    return current


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


class TransformPlugin(PluginBase):
    """数据提取与变换能力。"""

    name = "transform"
    description = "数据提取与变换：路径/索引/键读取、字符串处理、JSON、正则、比较"

    @engine_function(
        name="append",
        description="向列表追加元素，返回追加后的完整 JSON 数组字符串",
        parameters=_params(
            ("list_var", "value"),
            list_var={
                "type": "string",
                "description": "原列表（JSON 数组字符串；空字符串视为空列表）",
            },
            value={"type": "object", "description": "要追加的值"},
        ),
        returns={"list": "str"},
        output_param="save_to",
    )
    def append(self, list_var: object, value: object) -> FunctionResult:
        if isinstance(list_var, list):
            items = list(list_var)
        else:
            try:
                items = json.loads(str(list_var)) if list_var else []
            except (TypeError, ValueError):
                items = []
            if not isinstance(items, list):
                items = []
        items.append(value)
        return FunctionResult.success(json.dumps(items, ensure_ascii=False))

    @engine_function(
        name="dict_set",
        description="向字典设置 KV，返回设置后的完整 JSON 对象字符串",
        parameters=_params(
            ("dict_var", "key", "value"),
            dict_var={
                "type": "string",
                "description": "原字典（JSON 对象字符串；空字符串视为空字典）",
            },
            key={"type": "string", "description": "键"},
            value={"type": "object", "description": "值"},
        ),
        returns={"dict": "str"},
        output_param="save_to",
    )
    def dict_set(self, dict_var: object, key: str, value: object) -> FunctionResult:
        if isinstance(dict_var, dict):
            data = dict(dict_var)
        else:
            try:
                data = json.loads(str(dict_var)) if dict_var else {}
            except (TypeError, ValueError):
                data = {}
            if not isinstance(data, dict):
                data = {}
        data[str(key)] = value
        return FunctionResult.success(json.dumps(data, ensure_ascii=False))

    @engine_function(
        name="get_path",
        description=(
            "按点路径从嵌套列表/字典中取值，如 path='0.a.b.1' 表示取第 0 个元素的 "
            "a 字段的 b 字段的第 1 个元素；也支持 a[0].b 写法"
        ),
        parameters=_params(
            ("data", "path"),
            data={"type": "object", "description": "列表或字典"},
            path={"type": "string", "description": "点路径，如 0.a.b.1"},
            required={"type": "boolean", "description": "路径不存在是否失败（默认 true）"},
            default={"type": "object", "description": "required=false 时返回的默认值"},
        ),
        returns={"value": "object"},
    )
    def get_path(
        self,
        data: Any,
        path: str,
        required: bool = True,
        default: Any = None,
    ) -> FunctionResult:
        try:
            return FunctionResult.success(_read_path(data, path))
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            if not required:
                return FunctionResult.success(default)
            return _failure(f"路径读取失败: {exc}")

    @engine_function(
        name="get_index",
        description="获取列表/元组指定索引（支持负数索引）",
        parameters=_params(
            ("data", "index"),
            data={"type": "array", "items": {}, "description": "列表"},
            index={"type": "integer", "description": "索引"},
            required={"type": "boolean", "description": "索引不存在是否失败（默认 true）"},
            default={"type": "object", "description": "required=false 时返回的默认值"},
        ),
        returns={"value": "object"},
    )
    def get_index(
        self, data: list[Any], index: int, required: bool = True, default: Any = None
    ) -> FunctionResult:
        try:
            return FunctionResult.success(data[int(index)])
        except (IndexError, ValueError, TypeError):
            return FunctionResult.success(default) if not required else _failure("索引越界")

    @engine_function(
        name="get_key",
        description="获取字典指定键的值",
        parameters=_params(
            ("data", "key"),
            data={"type": "object", "description": "字典"},
            key={"type": "string", "description": "键名"},
            required={"type": "boolean", "description": "键不存在是否失败（默认 true）"},
            default={"type": "object", "description": "required=false 时返回的默认值"},
        ),
        returns={"value": "object"},
    )
    def get_key(
        self, data: dict, key: str, required: bool = True, default: Any = None
    ) -> FunctionResult:
        if isinstance(data, dict) and key in data:
            return FunctionResult.success(data[key])
        return FunctionResult.success(default) if not required else _failure(f"键不存在: {key}")

    @engine_function(
        name="split",
        description="按分隔符把字符串切分为列表（maxsplit=-1 表示不限制）",
        parameters=_params(
            ("text", "separator"),
            text={"type": "string", "description": "待切分文本"},
            separator={"type": "string", "description": "分隔符"},
            maxsplit={"type": "integer", "description": "最大切分次数（默认 -1）"},
        ),
        returns={"values": "object"},
    )
    def split(self, text: str, separator: str, maxsplit: int = -1) -> FunctionResult:
        if not separator:
            return _failure("分隔符不能为空")
        return FunctionResult.success(text.split(separator, int(maxsplit)))

    @engine_function(
        name="join",
        description="把列表元素用分隔符拼接成字符串",
        parameters=_params(
            ("values", "separator"),
            values={"type": "array", "items": {}, "description": "待拼接列表"},
            separator={"type": "string", "description": "分隔符"},
        ),
        returns={"text": "str"},
    )
    def join(self, values: list[Any], separator: str) -> FunctionResult:
        if not isinstance(values, (list, tuple)):
            return _failure("values 必须是列表")
        return FunctionResult.success(str(separator).join(_as_text(v) for v in values))

    @engine_function(
        name="concat",
        description="顺序拼接文本片段（按 a→e，忽略空值，可指定 separator）",
        parameters=_params(
            ("a", "b"),
            a={"type": "object", "description": "第 1 段"},
            b={"type": "object", "description": "第 2 段"},
            c={"type": "object", "description": "第 3 段（可选）"},
            d={"type": "object", "description": "第 4 段（可选）"},
            e={"type": "object", "description": "第 5 段（可选）"},
            separator={"type": "string", "description": "片段间分隔符（默认空）"},
        ),
        returns={"text": "str"},
    )
    def concat(
        self,
        a: Any,
        b: Any,
        c: Any = "",
        d: Any = "",
        e: Any = "",
        separator: str = "",
    ) -> str:
        parts = [a, b, c, d, e]
        return str(separator).join(
            _as_text(part) for part in parts if part is not None and part != ""
        )

    @engine_function(
        name="format",
        description="用 values 字典替换模板中的 {name} 占位符",
        parameters=_params(
            ("template", "values"),
            template={"type": "string", "description": "模板，如 http://{host}:{port}/api"},
            values={"type": "object", "description": "占位符取值字典"},
        ),
        returns={"text": "str"},
    )
    def format(self, template: str, values: dict) -> FunctionResult:
        if not isinstance(values, dict):
            return _failure("values 必须是字典")
        pattern = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return _as_text(values[key]) if key in values else match.group(0)

        return FunctionResult.success(pattern.sub(replace, str(template)))

    @engine_function(
        name="contains",
        description="判断字符串是否包含子串（ignore_case 可忽略大小写）",
        parameters=_params(
            ("text", "needle"),
            text={"type": "string", "description": "原文本"},
            needle={"type": "string", "description": "子串"},
            ignore_case={"type": "boolean", "description": "是否忽略大小写"},
        ),
        returns={"result": "bool"},
    )
    def contains(self, text: str, needle: str, ignore_case: bool = False) -> bool:
        source, target = str(text), str(needle)
        if ignore_case:
            source, target = source.lower(), target.lower()
        return target in source

    @engine_function(
        name="index_of",
        description="返回子串首次出现位置，未找到返回 -1",
        parameters=_params(
            ("text", "needle"),
            text={"type": "string", "description": "原文本"},
            needle={"type": "string", "description": "子串"},
            ignore_case={"type": "boolean", "description": "是否忽略大小写"},
        ),
        returns={"index": "int"},
    )
    def index_of(self, text: str, needle: str, ignore_case: bool = False) -> int:
        source, target = str(text), str(needle)
        if ignore_case:
            source, target = source.lower(), target.lower()
        return source.find(target)

    @engine_function(
        name="replace",
        description="替换字符串中的子串（count=-1 表示全部替换）",
        parameters=_params(
            ("text", "old", "new"),
            text={"type": "string", "description": "原文本"},
            old={"type": "string", "description": "旧子串"},
            new={"type": "string", "description": "新子串"},
            count={"type": "integer", "description": "最多替换次数（默认 -1）"},
        ),
        returns={"text": "str"},
    )
    def replace(self, text: str, old: str, new: str, count: int = -1) -> str:
        return str(text).replace(str(old), str(new), int(count))

    @engine_function(
        name="strip",
        description="去除字符串首尾空白或指定字符",
        parameters=_params(
            ("text",),
            text={"type": "string", "description": "原文本"},
            chars={"type": "string", "description": "要剔除的字符集合（默认空白）"},
        ),
        returns={"text": "str"},
    )
    def strip(self, text: str, chars: str | None = None) -> str:
        return str(text).strip(chars) if chars is not None else str(text).strip()

    @engine_function(
        name="length",
        description="返回字符串/列表/字典的长度",
        parameters=_params(("value",), value={"type": "object", "description": "待求长度值"}),
        returns={"length": "int"},
    )
    def length(self, value: Any) -> FunctionResult:
        if not isinstance(value, (str, list, tuple, dict)):
            return _failure("value 必须是字符串/列表/字典")
        return FunctionResult.success(len(value))

    @engine_function(
        name="slice",
        description="对列表或字符串切片（支持 start/end/step）",
        parameters=_params(
            ("value",),
            value={"type": "object", "description": "列表或字符串"},
            start={"type": "integer", "description": "起始索引（默认 0）"},
            end={"type": "integer", "description": "结束索引（默认到末尾）"},
            step={"type": "integer", "description": "步长（默认 1）"},
        ),
        returns={"value": "object"},
    )
    def slice(
        self,
        value: Any,
        start: int = 0,
        end: int | None = None,
        step: int = 1,
    ) -> FunctionResult:
        if not isinstance(value, (str, list, tuple)):
            return _failure("value 必须是字符串/列表")
        end_index = int(end) if end is not None else None
        return FunctionResult.success(value[int(start) : end_index : int(step)])

    @engine_function(
        name="keys",
        description="返回字典的全部键列表",
        parameters=_params(("data",), data={"type": "object", "description": "字典"}),
        returns={"keys": "object"},
    )
    def keys(self, data: dict) -> FunctionResult:
        if not isinstance(data, dict):
            return _failure("data 必须是字典")
        return FunctionResult.success(list(data.keys()))

    @engine_function(
        name="values",
        description="返回字典的全部值列表",
        parameters=_params(("data",), data={"type": "object", "description": "字典"}),
        returns={"values": "object"},
    )
    def values(self, data: dict) -> FunctionResult:
        if not isinstance(data, dict):
            return _failure("data 必须是字典")
        return FunctionResult.success(list(data.values()))

    @engine_function(
        name="compare",
        description=(
            "比较两个值，op 支持 eq/ne/gt/ge/lt/le/contains/startswith/endswith，"
            "返回布尔结果"
        ),
        parameters=_params(
            ("a", "b"),
            a={"type": "object", "description": "值 a"},
            b={"type": "object", "description": "值 b"},
            op={
                "type": "string",
                "description": "比较操作（默认 eq）",
                "enum": [
                    "eq",
                    "ne",
                    "gt",
                    "ge",
                    "lt",
                    "le",
                    "contains",
                    "startswith",
                    "endswith",
                ],
            },
            ignore_case={"type": "boolean", "description": "字符串比较是否忽略大小写"},
        ),
        returns={"result": "bool"},
    )
    def compare(
        self,
        a: Any,
        b: Any,
        op: str = "eq",
        ignore_case: bool = False,
    ) -> FunctionResult:
        left, right = a, b
        if ignore_case and isinstance(left, str) and isinstance(right, str):
            left, right = left.lower(), right.lower()
        handlers = {
            "eq": lambda: left == right,
            "ne": lambda: left != right,
            "gt": lambda: left > right,
            "ge": lambda: left >= right,
            "lt": lambda: left < right,
            "le": lambda: left <= right,
            "contains": lambda: str(right) in str(left),
            "startswith": lambda: str(left).startswith(str(right)),
            "endswith": lambda: str(left).endswith(str(right)),
        }
        handler = handlers.get(str(op))
        if handler is None:
            return _failure(f"不支持的比较操作: {op}")
        try:
            return FunctionResult.success(bool(handler()))
        except TypeError as exc:
            return _failure(f"无法比较: {exc}")

    @engine_function(
        name="to_string",
        description="把任意值转换为字符串（JSON 对象会序列化）",
        parameters=_params(("value",), value={"type": "object", "description": "待转换值"}),
        returns={"text": "str"},
    )
    def to_string(self, value: Any) -> str:
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=False)
        return _as_text(value)

    @engine_function(
        name="to_int",
        description="把文本/数字转换为整数（失败返回错误）",
        parameters=_params(("value",), value={"type": "object", "description": "待转换值"}),
        returns={"value": "int"},
    )
    def to_int(self, value: Any) -> FunctionResult:
        try:
            return FunctionResult.success(int(value))
        except (TypeError, ValueError) as exc:
            return _failure(f"无法转换为整数: {exc}")

    @engine_function(
        name="to_number",
        description="把文本/数字转换为浮点数（失败返回错误）",
        parameters=_params(("value",), value={"type": "object", "description": "待转换值"}),
        returns={"value": "float"},
    )
    def to_number(self, value: Any) -> FunctionResult:
        try:
            return FunctionResult.success(float(value))
        except (TypeError, ValueError) as exc:
            return _failure(f"无法转换为数字: {exc}")

    @engine_function(
        name="to_bool",
        description="把常见真假值转换为布尔（true/1/yes/on 为真，false/0/no/off/空为假）",
        parameters=_params(("value",), value={"type": "object", "description": "待转换值"}),
        returns={"value": "bool"},
    )
    def to_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}

    @engine_function(
        name="json_parse",
        description="解析 JSON 文本为对象/列表",
        parameters=_params(("text",), text={"type": "string", "description": "JSON 文本"}),
        returns={"value": "object"},
    )
    def json_parse(self, text: str) -> FunctionResult:
        try:
            return FunctionResult.success(json.loads(text))
        except (TypeError, ValueError) as exc:
            return _failure(f"JSON 解析失败: {exc}")

    @engine_function(
        name="json_dumps",
        description="把对象/列表序列化为 JSON 文本",
        parameters=_params(
            ("value",),
            value={"type": "object", "description": "待序列化值"},
            indent={"type": "integer", "description": "缩进空格数（默认 0）"},
        ),
        returns={"text": "str"},
    )
    def json_dumps(self, value: Any, indent: int = 0) -> str:
        return json.dumps(value, ensure_ascii=False, indent=int(indent) or None)

    @engine_function(
        name="regex_match",
        description="判断文本是否匹配正则表达式（full=true 时要求完全匹配）",
        parameters=_params(
            ("text", "pattern"),
            text={"type": "string", "description": "原文本"},
            pattern={"type": "string", "description": "正则表达式"},
            full={"type": "boolean", "description": "是否要求完全匹配"},
            ignore_case={"type": "boolean", "description": "是否忽略大小写"},
        ),
        returns={"result": "bool"},
    )
    def regex_match(
        self,
        text: str,
        pattern: str,
        full: bool = False,
        ignore_case: bool = False,
    ) -> FunctionResult:
        flags = re.IGNORECASE if ignore_case else 0
        try:
            matched = (
                re.fullmatch(pattern, text, flags)
                if full
                else re.search(pattern, text, flags)
            )
        except re.error as exc:
            return _failure(f"正则错误: {exc}")
        return FunctionResult.success(matched is not None)

    @engine_function(
        name="regex_extract",
        description="按正则提取第一个匹配（group 指定分组，默认 0），未匹配返回错误",
        parameters=_params(
            ("text", "pattern"),
            text={"type": "string", "description": "原文本"},
            pattern={"type": "string", "description": "正则表达式"},
            group={"type": "integer", "description": "分组编号（默认 0）"},
            ignore_case={"type": "boolean", "description": "是否忽略大小写"},
        ),
        returns={"text": "str"},
    )
    def regex_extract(
        self,
        text: str,
        pattern: str,
        group: int = 0,
        ignore_case: bool = False,
    ) -> FunctionResult:
        flags = re.IGNORECASE if ignore_case else 0
        try:
            match = re.search(pattern, text, flags)
        except re.error as exc:
            return _failure(f"正则错误: {exc}")
        if match is None:
            return _failure("正则未匹配")
        try:
            return FunctionResult.success(match.group(int(group)))
        except IndexError:
            return _failure(f"正则分组不存在: {group}")

    @engine_function(
        name="regex_findall",
        description="按正则提取全部匹配并返回列表",
        parameters=_params(
            ("text", "pattern"),
            text={"type": "string", "description": "原文本"},
            pattern={"type": "string", "description": "正则表达式"},
            ignore_case={"type": "boolean", "description": "是否忽略大小写"},
        ),
        returns={"values": "object"},
    )
    def regex_findall(
        self, text: str, pattern: str, ignore_case: bool = False
    ) -> FunctionResult:
        flags = re.IGNORECASE if ignore_case else 0
        try:
            return FunctionResult.success(re.findall(pattern, text, flags))
        except re.error as exc:
            return _failure(f"正则错误: {exc}")


plugin = TransformPlugin()

__all__ = ["TransformPlugin", "plugin"]
