"""插件管理服务（plugin-management spec）。

- 启动初始化：扫描预置插件 → 写/刷新 ``builtin`` 记录（只读，``source`` NULL）。
- CRUD：自定义插件源码存 DB；校验（语法 + 仅标准库约束 + 可加载）通过才落库。
- 重载：保存成功后重新加载进共享注册表。
- 关联查询与删除置空：删除插件时扫描引用其函数的行为树，批量把 FunctionCall
  的 ``function`` 引用置空（持久化修改文档）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from autobranch.plugin_system import (
    PluginRegistry,
    check_plugin_source,
    load_builtin_plugins,
    load_plugin_from_source,
)
from autobranch.server.db import get_db
from autobranch.server.deps import get_plugin_registry, get_plugins_dir
from autobranch.server.errors import AppError
from autobranch.server.models import Plugin, Tree
from autobranch.server.models.plugin import KIND_BUILTIN, KIND_CUSTOM
from autobranch.server.schemas.plugin import (
    FunctionInfo,
    PluginCheckOut,
    PluginCreate,
    PluginDetailOut,
    PluginOut,
    PluginUpdate,
)

DbSession = Annotated[Session, Depends(get_db)]
Registry = Annotated[PluginRegistry, Depends(get_plugin_registry)]
PluginsDir = Annotated[str | None, Depends(get_plugins_dir)]

#: 匹配 yaml 中的 ``function: <name>`` 行（FunctionCall 节点引用，全名含 `.`/`-`）。
_FUNCTION_LINE = re.compile(
    r"^(?P<indent>\s*function:\s*)(?P<q>['\"]?)(?P<name>[A-Za-z_][\w.-]*)(?P=q)[ \t]*$",
    re.MULTILINE,
)


class PluginService:
    """插件管理服务（会话 / 注册表经 DI 注入）。"""

    def __init__(self, db: DbSession, registry: Registry, plugins_dir: PluginsDir = None) -> None:
        self.db = db
        self.registry = registry
        self.plugins_dir = plugins_dir

    # ------------------------------------------------------------- 初始化

    def init_builtins(self) -> list[str]:
        """扫描预置插件并同步 ``builtin`` 记录（只读，``source`` 恒 NULL）。"""
        if not self.plugins_dir:
            return []
        loaded = load_builtin_plugins(self.registry, Path(self.plugins_dir))
        for name in loaded:
            plugin = self.registry.plugin(name)
            if plugin is None:
                continue
            funcs = json.dumps(
                [f"{name}.{s.name}" for s in plugin.function_defs()], ensure_ascii=False
            )
            row = self._find(name)
            if row is None:
                self.db.add(
                    Plugin(
                        name=name,
                        kind=KIND_BUILTIN,
                        description=plugin.description or "",
                        functions=funcs,
                        source=None,
                    )
                )
            else:
                row.kind = KIND_BUILTIN
                row.description = plugin.description or ""
                row.functions = funcs
                row.source = None
        self.db.commit()
        return loaded

    # ------------------------------------------------------------- 查询

    def list_all(self) -> list[PluginOut]:
        rows = self.db.scalars(select(Plugin).order_by(Plugin.id)).all()
        return [PluginOut.model_validate(r) for r in rows]

    def list_functions(self) -> list[FunctionInfo]:
        """跨插件聚合全部已注册函数（全名 + 结构化定义），供编辑器选择器使用。"""
        return [
            FunctionInfo(
                full_name=s.full_name,
                plugin=s.plugin,
                name=s.name,
                description=s.description,
                returns=list(s.returns),
                parameters=s.parameters,
            )
            for s in self.registry.functions().values()
        ]

    def get(self, name: str) -> Plugin:
        row = self._find(name)
        if row is None:
            raise AppError(404, f"插件不存在 (name={name})")
        return row

    def get_detail(self, name: str) -> PluginDetailOut:
        detail = PluginDetailOut.model_validate(self.get(name))
        if detail.kind == KIND_BUILTIN and self.plugins_dir:
            # 内置插件只读：从文件系统读取源码供查看（DB 的 source 恒 NULL）
            detail.source = self._read_builtin_source(name)
        return detail

    def _read_builtin_source(self, name: str) -> str | None:
        if not self.plugins_dir:
            return None
        path = Path(self.plugins_dir) / name / "__init__.py"
        try:
            return path.read_text(encoding="utf-8") if path.is_file() else None
        except OSError:
            return None

    def references(self, name: str) -> list[str]:
        """引用该插件函数的行为树名列表（扫描 FunctionCall 的 ``function`` 引用）。"""
        funcs = self._function_names(name)
        if not funcs:
            return []
        hits: list[str] = []
        for tree in self.db.scalars(select(Tree)).all():
            if any(self._has_ref(tree.content, fn) for fn in funcs):
                hits.append(tree.name)
        return hits

    # ------------------------------------------------------------- 校验 / 变更

    def check(self, name: str, source: str) -> PluginCheckOut:
        ok, errors = check_plugin_source(source)
        if ok:
            ok, errors = self._probe_load(name, source)
        return PluginCheckOut(ok=ok, errors=errors)

    def create(self, payload: PluginCreate) -> PluginOut:
        if self._find(payload.name) is not None:
            raise AppError(409, f"插件名已存在 (name={payload.name})")
        ok, errors = check_plugin_source(payload.source)
        if not ok:
            raise AppError(422, {"errors": errors})
        ok, errors = self._probe_load(payload.name, payload.source)
        if not ok:
            raise AppError(422, {"errors": errors})
        row = Plugin(
            name=payload.name,
            kind=KIND_CUSTOM,
            description=self._describe(payload.name, payload.source),
            functions="[]",
            source=payload.source,
        )
        self.db.add(row)
        self._commit_or_conflict()
        load_plugin_from_source(self.registry, payload.name, payload.source)
        row.functions = json.dumps(self._function_names(payload.name), ensure_ascii=False)
        self.db.commit()
        self.db.refresh(row)
        return PluginOut.model_validate(row)

    def update(self, name: str, payload: PluginUpdate) -> PluginOut:
        row = self.get(name)
        if row.kind == KIND_BUILTIN:
            raise AppError(403, "预置插件只读，不可修改")
        ok, errors = check_plugin_source(payload.source)
        if not ok:
            raise AppError(422, {"errors": errors})
        try:
            load_plugin_from_source(self.registry, name, payload.source, allow_override=True)
        except Exception as exc:  # noqa: BLE001
            raise AppError(422, {"errors": [{"type": "runtime", "message": str(exc)}]}) from exc
        row.source = payload.source
        row.description = self._describe(name, payload.source)
        row.functions = json.dumps(self._function_names(name), ensure_ascii=False)
        self.db.commit()
        self.db.refresh(row)
        return PluginOut.model_validate(row)

    def delete(self, name: str) -> list[str]:
        """删除自定义插件；引用其函数的行为树中 FunctionCall 引用置空。"""
        row = self.get(name)
        if row.kind == KIND_BUILTIN:
            raise AppError(403, "预置插件只读，不可删除")
        affected = self.references(name)
        funcs = self._function_names(name)
        if affected:
            for tree in self.db.scalars(select(Tree)).all():
                if tree.name not in affected:
                    continue
                new_content = tree.content
                for fn in funcs:
                    new_content = self._nullify_ref(new_content, fn)
                if new_content != tree.content:
                    tree.content = new_content
        self.registry.unregister(name)
        self.db.delete(row)
        self.db.commit()
        return affected

    # ------------------------------------------------------------- 内部

    def _find(self, name: str) -> Plugin | None:
        return self.db.scalars(select(Plugin).where(Plugin.name == name)).first()

    def _function_names(self, name: str) -> list[str]:
        return [s.full_name for s in self.registry.functions_of(name)]

    def _probe_load(self, name: str, source: str) -> tuple[bool, list[dict]]:
        """试加载（注册后立即撤销，不落库）：验证可执行 + 插件名一致。"""
        try:
            load_plugin_from_source(self.registry, name, source, allow_override=True)
        except Exception as exc:  # noqa: BLE001
            return False, [
                {
                    "line": None,
                    "column": None,
                    "type": "runtime",
                    "message": str(exc),
                    "constraint": "可加载",
                }
            ]
        finally:
            self.registry.unregister(name)
        return True, []

    def _describe(self, name: str, source: str) -> str:
        try:
            load_plugin_from_source(self.registry, name, source, allow_override=True)
            plugin = self.registry.plugin(name)
            desc = (plugin.description if plugin else "") or ""
        except Exception:  # noqa: BLE001
            desc = ""
        finally:
            self.registry.unregister(name)
        return desc[:500]

    def _has_ref(self, content: str, fn: str) -> bool:
        return any(m.group("name") == fn for m in _FUNCTION_LINE.finditer(content))

    def _nullify_ref(self, content: str, fn: str) -> str:
        def repl(match: re.Match) -> str:
            if match.group("name") == fn:
                return f"{match.group('indent')}null"
            return match.group(0)

        return _FUNCTION_LINE.sub(repl, content)

    def _commit_or_conflict(self) -> None:
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise AppError(409, "插件名已存在") from None


__all__ = ["PluginService"]
