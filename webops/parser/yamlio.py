"""yaml 文本 → dict 的统一规范化入口（M2 数据入口，任务 1.3）。

优先使用 PyYAML（若环境已安装）；缺失时回落到标准库实现的
**YAML 子集解析器**（``_SubsetLoader``），覆盖行为树文档所需的常见结构：

- 缩进层级映射 / 序列（含 ``- key: value`` 的多行键续行）
- 单双引号字符串、数字、布尔、null
- 行内流式 ``[a, b]`` / ``{k: v}``（含嵌套与引号）
- 注释剥离（引号/花括号内 ``#`` 不视为注释）
- 块标量 ``|`` / ``>``（基础支持）

子集解析器不覆盖 YAML 完整规范（别名/锚点、多文档流、制表符缩进等），
生产环境建议安装 PyYAML。本模块保证：yaml 文本与 dict 两种入口经
``normalize_document`` 统一收敛，行为一致；非法输入抛
:class:`InvalidDocumentError`。
"""

from __future__ import annotations

import re

from webops.parser.errors import InvalidDocumentError

_INT_RE = re.compile(r"[+-]?\d+$")
_FLOAT_RE = re.compile(r"[+-]?\d+\.\d+$")


def normalize_document(data: str | dict) -> dict:
    """统一文档源 → dict（yaml 文本先转 dict，再走同一解析路径）。

    :raises InvalidDocumentError: 输入既不是合法 yaml 也不是 dict，或
        解析结果不是顶层映射（dict）。
    """
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        loaded = _load_yaml(data)
        if not isinstance(loaded, dict):
            raise InvalidDocumentError(
                "行为树文档必须是 yaml 顶层映射（dict）；若未安装 PyYAML，"
                "标准库子集解析器仅支持缩进式映射/序列"
            )
        return loaded
    raise InvalidDocumentError(
        f"不支持的文档源类型: {type(data).__name__}（期望 yaml 文本或 dict）"
    )


def _load_yaml(text: str) -> object:
    """优先 PyYAML，缺失时回落标准库子集解析器。"""
    try:
        import yaml  # PyYAML（可选依赖）

        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:  # pragma: no cover - 依赖 PyYAML 分支
            raise InvalidDocumentError(f"yaml 解析失败: {exc}") from exc
    except ImportError:
        return _SubsetLoader(text).load()


def _strip_comment(line: str) -> str:
    """剥离注释（引号或花括号内 ``#`` 不视为注释）。"""
    out: list[str] = []
    quote: str | None = None
    depth = 0
    for i, ch in enumerate(line):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            continue
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == "#" and depth == 0 and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _split_key(s: str) -> tuple[str | None, str]:
    """切分映射项 ``key: value``。

    ``:`` 须后随空格或行尾且不在引号/流式括号内；否则视为标量
    （如 ``https://x``、``{{$this/账号}}`` 不会被误切分）。
    """
    depth = 0
    quote: str | None = None
    for i, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            continue
        if ch in "[{":
            depth += 1
            continue
        if ch in "]}":
            depth -= 1
            continue
        if ch == ":" and depth == 0:
            nxt = s[i + 1] if i + 1 < len(s) else ""
            if nxt == " " or nxt == "":
                return s[:i].strip(), s[i + 1 :].strip()
    return None, s


def _split_flow(s: str) -> list[str]:
    """按顶层逗号切分流式内容（引号与嵌套括号内不切）。"""
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    quote: str | None = None
    for ch in s:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            cur.append(ch)
            continue
        if ch in "[{":
            depth += 1
            cur.append(ch)
            continue
        if ch in "]}":
            depth -= 1
            cur.append(ch)
            continue
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    if "".join(cur).strip() or not s.strip():
        parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _split_flow_entry(s: str) -> tuple[str, str | None]:
    """切分流式映射项 ``key: value``（顶层冒号）。"""
    depth = 0
    quote: str | None = None
    for i, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            continue
        if ch in "[{":
            depth += 1
            continue
        if ch in "]}":
            depth -= 1
            continue
        if ch == ":" and depth == 0:
            return s[:i].strip(), s[i + 1 :].strip()
    return s.strip(), None


def _has_flow_colon(s: str) -> bool:
    """流式内容是否含顶层冒号（用于判定 ``{...}`` 是否为映射）。"""
    return _split_flow_entry(s)[1] is not None


def _parse_flow(s: str) -> object:
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        return [_parse_flow(x) for x in _split_flow(s[1:-1])]
    if s.startswith("{") and s.endswith("}") and _has_flow_colon(s[1:-1]):
        d: dict[str, object] = {}
        for part in _split_flow(s[1:-1]):
            key, val = _split_flow_entry(part)
            if key is None:
                continue
            d[key] = _parse_flow(val) if val is not None else None
        return d
    return _scalar_value(s)


def _scalar_value(s: str) -> object:
    """标量解析：引号、null、布尔、数字、字符串。"""
    s = s.strip()
    if not s:
        return None
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        inner = s[1:-1]
        if s[0] == '"':
            return inner.replace('\\"', '"').replace("\\n", "\n")
        return inner
    low = s.lower()
    if low in ("null", "~"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if _INT_RE.fullmatch(s):
        return int(s)
    if _FLOAT_RE.fullmatch(s):
        return float(s)
    return s


class _SubsetLoader:
    """标准库 YAML 子集解析器（缩进敏感，行为树文档常见结构）。"""

    def __init__(self, text: str) -> None:
        self._lines: list[tuple[int, str]] = []
        for raw in text.splitlines():
            stripped = _strip_comment(raw)
            if not stripped.strip():
                continue
            indent = len(stripped) - len(stripped.lstrip(" "))
            self._lines.append((indent, stripped[indent:]))
        self._i = 0

    def load(self) -> object:
        if not self._lines:
            return None
        indent, content = self._lines[0]
        if content.startswith("-"):
            value, _ = self._sequence(0, indent)
        else:
            key, _ = _split_key(content)
            if key is None:
                value = _scalar_value(content)
            else:
                value, _ = self._mapping(0, indent)
        return value

    def _value_at(self, i: int, min_indent: int) -> tuple[object, int]:
        if i >= len(self._lines):
            return None, i
        indent, content = self._lines[i]
        if indent < min_indent:
            return None, i
        if content.startswith("-"):
            return self._sequence(i, indent)
        key, _ = _split_key(content)
        if key is not None:
            return self._mapping(i, indent)
        return _scalar_value(content), i + 1

    def _mapping(self, i: int, indent: int) -> tuple[dict[str, object], int]:
        d: dict[str, object] = {}
        n = len(self._lines)
        while i < n:
            ind, content = self._lines[i]
            if ind != indent or content.startswith("-"):
                break
            key, rest = _split_key(content)
            if key is None:
                break
            if rest in ("|", ">") or rest.endswith(("|", ">")):
                value, i = self._block_scalar(i + 1, indent)
            elif rest == "":
                value, i = self._value_at(i + 1, indent + 2)
            else:
                value = _parse_flow(rest)
                i += 1
            d[key] = value
        return d, i

    def _sequence(self, i: int, indent: int) -> tuple[list[object], int]:
        items: list[object] = []
        n = len(self._lines)
        while i < n:
            ind, content = self._lines[i]
            if ind != indent or not content.startswith("-"):
                break
            rest = content[1:].lstrip(" ")
            c = ind + 2  # 项内容起始列
            if rest == "":
                value, i = self._value_at(i + 1, c + 2)
                items.append(value)
                continue
            key, r = _split_key(rest)
            if key is None:
                items.append(_scalar_value(rest))
                i += 1
                continue
            if r in ("|", ">") or r.endswith(("|", ">")):
                v, ni = self._block_scalar(i + 1, c)
            elif r == "":
                v, ni = self._value_at(i + 1, c + 2)
            else:
                v = _parse_flow(r)
                ni = i + 1
            d: dict[str, object] = {key: v}
            i = ni
            while i < n:
                ind2, content2 = self._lines[i]
                if ind2 != c or content2.startswith("-"):
                    break
                k2, r2 = _split_key(content2)
                if k2 is None:
                    break
                if r2 in ("|", ">") or r2.endswith(("|", ">")):
                    v2, ni2 = self._block_scalar(i + 1, c)
                elif r2 == "":
                    v2, ni2 = self._value_at(i + 1, c + 2)
                else:
                    v2 = _parse_flow(r2)
                    ni2 = i + 1
                d[k2] = v2
                i = ni2
            items.append(d)
        return items, i

    def _block_scalar(self, i: int, key_indent: int) -> tuple[str, int]:
        """块标量 ``|`` / ``>``：收集后续更深缩进行，以换行连接。"""
        lines: list[str] = []
        n = len(self._lines)
        while i < n:
            ind, content = self._lines[i]
            if ind <= key_indent:
                break
            lines.append(content)
            i += 1
        return "\n".join(lines), i
