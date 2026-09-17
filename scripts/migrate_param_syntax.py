"""参数语法迁移：中文变量名 → 语义英文 + 旧语法 → Param./NewParam.

用法：
  python scripts/migrate_param_syntax.py          # dry-run：输出每树 diff，不改库
  python scripts/migrate_param_syntax.py --apply  # 写回 data/autobranch.db

幂等：对已迁移内容再次运行无变化。
"""

from __future__ import annotations

import difflib
import re
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "autobranch.db"

MAPPING = {
    "苹果金额": "appleAmount",
    "香蕉金额": "bananaAmount",
    "水果合计": "fruitTotal",
    "结果": "result",
    "积": "product",
    "入参1": "input1",
}

TYPE_TOKENS = r"(?:str|int|float|bool|page_ref|object)"
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"

_GET_OLD = re.compile(r"\[\[\s*get:\s*(?:this/)?([^\s\[\]]+?)\s*\]\]")
_SET_OLD = re.compile(
    r"\[\[\s*set:(" + TYPE_TOKENS + r":)?\s*(?:this/)?([^\s\[\]:]+?)\s*\]\]"
)


def _declared_names(content: str) -> set[str]:
    """收集迁移后文档内的已声明变量名（inputs 键 + NewParam 目标 + returns 键）。"""
    names: set[str] = set()
    for m in re.finditer(r"inputs:\s*\{([^}]*)\}", content):
        for k in re.findall(r"(" + _IDENT + r")\s*:", m.group(1)):
            names.add(k)
    for m in re.finditer(r"^\s+(" + _IDENT + r")\s*:\s*" + TYPE_TOKENS + r"\s*$", content, re.M):
        names.add(m.group(1))
    for m in re.finditer(r"NewParam\.(" + _IDENT + r")(?::" + TYPE_TOKENS + r")?", content):
        names.add(m.group(1))
    return names


def _prefix_returns(content: str) -> str:
    """returns 键（多行块 + 内联 `{k: t}`）→ `NewParam.k`。"""

    def inline(m: re.Match) -> str:
        parts = [p.strip() for p in m.group(1).split(",")]
        fixed: list[str] = []
        for p in parts:
            mm = re.match(r"^(" + _IDENT + r")(\s*:\s*" + TYPE_TOKENS + r")$", p)
            if mm and not mm.group(1).startswith("NewParam."):
                fixed.append("NewParam." + mm.group(1) + mm.group(2))
            else:
                fixed.append(p)
        return "returns: {" + ", ".join(fixed) + "}"

    content = re.sub(r"returns:\s*\{([^}]*)\}", inline, content)

    lines = content.splitlines(keepends=True)
    out: list[str] = []
    in_returns = False
    returns_indent = 0
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.strip().startswith("returns:"):
            in_returns = True
            returns_indent = len(stripped) - len(stripped.lstrip())
            out.append(line)
            continue
        if in_returns:
            indent = len(stripped) - len(stripped.lstrip())
            if stripped.strip() == "":
                out.append(line)
                continue
            if indent <= returns_indent:
                in_returns = False
            else:
                m = re.match(
                    r"^(\s*)(" + _IDENT + r")(\s*:\s*" + TYPE_TOKENS + r"\s*)$", stripped
                )
                if m and not m.group(2).startswith("NewParam."):
                    line = line.replace(m.group(2), "NewParam." + m.group(2), 1)
                out.append(line)
                continue
        out.append(line)
    return "".join(out)


def _fix_args(content: str, declared: set[str]) -> str:
    """args（内联 `[..]` 与多行 `- item`）裸名命中声明变量 → `Param.x`。"""

    def convert(item: str) -> str:
        it = item.strip().strip('"').strip("'")
        if (
            re.fullmatch(_IDENT, it)
            and it in declared
            and not it.startswith("Param.")
            and not it.startswith("NewParam.")
        ):
            return "Param." + it
        return item.strip()

    def inline(m: re.Match) -> str:
        items = [convert(x) for x in m.group(1).split(",")]
        return "args: [" + ", ".join(items) + "]"

    content = re.sub(r"args:\s*\[([^\]]*)\]", inline, content)

    out: list[str] = []
    in_args = False
    args_indent = 0
    for line in content.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        if stripped.strip().startswith("args:"):
            in_args = True
            args_indent = len(stripped) - len(stripped.lstrip())
            out.append(line)
            continue
        if in_args:
            indent = len(stripped) - len(stripped.lstrip())
            if stripped.strip() == "":
                out.append(line)
                continue
            if indent <= args_indent:
                in_args = False
            else:
                m = re.match(r"^(\s*-\s*)(.+)$", stripped)
                if m:
                    converted = convert(m.group(2))
                    if converted != m.group(2):
                        line = line.replace(m.group(2), converted, 1)
                out.append(line)
                continue
        out.append(line)
    return "".join(out)


def migrate_content(content: str) -> str:
    """按规则迁移单棵树内容（幂等）。"""
    if not content:
        return content
    # 1) 中文变量名 → 语义英文（长名优先）
    for cn in sorted(MAPPING, key=len, reverse=True):
        content = content.replace(cn, MAPPING[cn])
    # 2) 旧语法 [[get:X]] → Param.X
    content = _GET_OLD.sub(lambda m: f"Param.{m.group(1)}", content)
    # 3) 旧语法 [[set[:t]:X]] → NewParam.X[:t]
    def _set(m: re.Match) -> str:
        typ = m.group(1)
        name = m.group(2)
        return f"NewParam.{name}" + (f":{typ[:-1]}" if typ else "")

    content = _SET_OLD.sub(_set, content)
    # 4) returns 键 → NewParam. 前缀
    content = _prefix_returns(content)
    # 5) args 裸名引用 → Param.x
    content = _fix_args(content, _declared_names(content))
    return content


def main() -> None:
    apply = "--apply" in sys.argv
    conn = sqlite3.connect(DB)
    rows = conn.execute("select id, name, content from trees").fetchall()
    any_diff = False
    for tid, tname, content in rows:
        migrated = migrate_content(content or "")
        if migrated == (content or ""):
            continue
        any_diff = True
        print(f"--- tree {tid} {tname} ---")
        for line in difflib.unified_diff(
            (content or "").splitlines(keepends=True),
            migrated.splitlines(keepends=True),
            fromfile="before",
            tofile="after",
        ):
            print(line.rstrip("\n"))
        if apply:
            conn.execute("update trees set content=? where id=?", (migrated, tid))
    if apply:
        conn.commit()
        print("applied" if any_diff else "no changes")
    else:
        print("dry-run (no changes); use --apply to write" if any_diff else "no differences")


if __name__ == "__main__":
    main()
