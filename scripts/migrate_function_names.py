"""一次性迁移脚本：把已保存行为树中 FunctionCall 的裸函数名改写为全名。

背景：函数标识从「裸函数名全局唯一」演进为「全名 ``插件名.函数名``（跨插件可
同名）」。旧库中的行为树 FunctionCall 引用裸名，需按插件归属改写为全名。

- 映射来源：当前插件注册表（预置插件 + DB 中的自定义插件）。
- 改写方式：**文本级**正则替换 ``function: <裸名>`` 行 → 全名，保留文档原始
  格式（缩进 / 引号 / 注释不重排）。
- 未能映射的裸名（如插件已被删除）：保留原值并输出到报告。

用法（autobranch conda 环境，项目根下）：
    python -m scripts.migrate_function_names [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autobranch.plugin_system import (  # noqa: E402
    PluginRegistry,
    load_builtin_plugins,
    load_plugin_from_source,
)
from autobranch.server.config import ServerConfig  # noqa: E402
from autobranch.server.db import configure_database, session_factory  # noqa: E402
from autobranch.server.models import Plugin, Tree  # noqa: E402
from autobranch.server.models.plugin import KIND_CUSTOM  # noqa: E402

PLUGINS_DIR = "autobranch/plugins"

_FUNCTION_LINE = re.compile(
    r"^(?P<indent>\s*function:\s*)(?P<q>['\"]?)(?P<name>[A-Za-z_][\w.-]*)(?P=q)[ \t]*$",
    re.MULTILINE,
)

#: 内联（flow-style）``function: <name>`` 引用，如 ``n3: {type: FunctionCall, function: add}``。
_FUNCTION_INLINE = re.compile(
    r"(?P<pre>function:[ \t]*)(?P<q>['\"]?)(?P<name>[A-Za-z_][\w.-]*)(?P=q)"
)


def build_registry() -> PluginRegistry:
    """构建当前插件注册表（预置 + DB 自定义），得到裸名 → 全名映射。"""
    reg = PluginRegistry()
    load_builtin_plugins(reg, PLUGINS_DIR)
    with session_factory()() as db:
        rows = db.scalars(select(Plugin).where(Plugin.kind == KIND_CUSTOM)).all()
        for row in rows:
            try:
                load_plugin_from_source(reg, row.name, row.source)
            except Exception as exc:  # noqa: BLE001 - 坏插件不应阻断迁移
                print(f"  [跳过自定义插件] {row.name}: {exc}")
    return reg


def bare_to_full(reg: PluginRegistry) -> dict[str, str]:
    """裸函数名 → 全名映射（旧注册表裸名全局唯一，映射确定）。"""
    mapping: dict[str, str] = {}
    for spec in reg.functions().values():
        prev = mapping.get(spec.name)
        if prev is not None and prev != spec.full_name:
            print(
                f"  [警告] 裸名 {spec.name} 对应多插件: {prev} / {spec.full_name}，跳过映射"
            )
            continue
        mapping[spec.name] = spec.full_name
    return mapping


def migrate_content(
    content: str, mapping: dict[str, str]
) -> tuple[str, list[tuple[str, str, str | None]]]:
    """改写单个文档文本；返回（新文本, [(树名, 裸名, 全名|None)]）。"""
    changed: list[tuple[str, str, str | None]] = []

    def repl(match: re.Match) -> str:
        name = match.group("name")
        full = mapping.get(name)
        if full:
            if full == name:
                return match.group(0)
            changed.append(("", name, full))
            return f"{match.group('indent')}{match.group('q')}{full}{match.group('q')}"
        # 未映射：已是全名（含点）或字面量（null/None/~）→ 跳过；裸标识符 → 报告
        if "." in name or name in ("null", "None", "~"):
            return match.group(0)
        changed.append(("", name, None))
        return match.group(0)

    new_content = _FUNCTION_LINE.sub(repl, content)

    def repl_inline(match: re.Match) -> str:
        name = match.group("name")
        full = mapping.get(name)
        if full and full != name:
            changed.append(("", name, full))
            return f"{match.group('pre')}{match.group('q')}{full}{match.group('q')}"
        return match.group(0)

    new_content = _FUNCTION_INLINE.sub(repl_inline, new_content)
    return new_content, changed


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移行为树 FunctionCall 裸函数名为全名")
    parser.add_argument("--dry-run", action="store_true", help="只报告不改写")
    args = parser.parse_args()

    settings = ServerConfig.load()
    configure_database(settings.db_path)
    print(f"数据库: {settings.db_path}")

    reg = build_registry()
    mapping = bare_to_full(reg)
    print(f"映射裸名 → 全名: {len(mapping)} 条")

    changed_trees = 0
    replaced = 0
    unmatched: list[tuple[str, str]] = []
    with session_factory()() as db:
        for tree in db.scalars(select(Tree)).all():
            new_content, changes = migrate_content(tree.content, mapping)
            for _, old, full in changes:
                if full is None:
                    unmatched.append((tree.name, old))
                else:
                    replaced += 1
            if new_content != tree.content:
                changed_trees += 1
                if not args.dry_run:
                    tree.content = new_content
        if not args.dry_run:
            db.commit()

    print(f"涉及行为树: {changed_trees} 棵")
    print(f"改写引用: {replaced} 处")
    if unmatched:
        print("未能映射（插件可能已删除，保留原值）:")
        for tname, old in unmatched:
            print(f"  - {tname}: {old}")
    print("完成（dry-run）" if args.dry_run else "完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
