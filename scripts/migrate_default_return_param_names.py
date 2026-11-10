"""迁移：参数名/节点 id ASCII、outputs 带类型、默认接收名、草稿状态。

用法：
    python -m scripts.migrate_default_return_param_names

规则：
- `trees.content`：非 ASCII 节点 id / inputs / outputs / returns 改名并改写本树引用；
- `outputs` 从列表转 `{名称: 类型}`，类型尽量从 NewParam/Define/来源节点推断，否则 object；
- 补全 ref/FunctionCall 默认接收名与类型；
- 迁移后所有行为树置 published；清空 experiences；
- `runs.content_snapshot` 不迁移。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from autobranch.parser.models import DocumentSource
from autobranch.parser.refs import MappingResolver
from autobranch.parser.yamlio import normalize_document
from autobranch.plugin_system import PluginRegistry, load_builtin_plugins
from autobranch.server.db import configure_database, session_factory
from autobranch.server.models import STATUS_PUBLISHED, Experience, Tree
from autobranch.server.services.normalize import normalize_tree_dict
from autobranch.server.services.tree_doc import dump

ROOT = Path(__file__).resolve().parents[1]
ASCII = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NEW_PARAM = re.compile(r"(?<![A-Za-z0-9_])NewParam\.([^\s:，,）)]+)(?::([A-Za-z_][A-Za-z0-9_]*))?")
SLOT_KEYS = ("body", "action", "then", "else")


def _replace_refs(value: object, mapping: dict[str, str], prefix: str) -> object:
    """递归替换字符串中的 ``<prefix>.<旧名>``。"""
    if isinstance(value, str):
        text = value
        for old, new in mapping.items():
            pattern = (
                rf"(?<![A-Za-z0-9_]){re.escape(prefix)}\.{re.escape(old)}"
                r"(?![A-Za-z0-9_])"
            )
            text = re.sub(pattern, f"{prefix}.{new}", text)
        return text
    if isinstance(value, list):
        return [_replace_refs(v, mapping, prefix) for v in value]
    if isinstance(value, dict):
        return {k: _replace_refs(v, mapping, prefix) for k, v in value.items()}
    return value


def _unique(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    i = 2
    while f"{base}{i}" in used:
        i += 1
    used.add(f"{base}{i}")
    return f"{base}{i}"


def _rename_nodes(data: dict) -> dict[str, str]:
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        return {}
    mapping: dict[str, str] = {}
    used = {nid for nid in nodes if ASCII.fullmatch(str(nid))}
    counter = 1
    for nid in list(nodes):
        if ASCII.fullmatch(str(nid)):
            continue
        while f"n{counter}" in used:
            counter += 1
        new = f"n{counter}"
        used.add(new)
        mapping[str(nid)] = new
    if not mapping:
        return {}
    new_nodes: dict[str, object] = {}
    for nid, body in nodes.items():
        new_id = mapping.get(str(nid), str(nid))
        if isinstance(body, dict):
            body = dict(body)
            for key in SLOT_KEYS:
                if body.get(key) in mapping:
                    body[key] = mapping[body[key]]
            if isinstance(body.get("actions"), list):
                body["actions"] = [mapping.get(str(c), c) for c in body["actions"]]
            if isinstance(body.get("branches"), list):
                branches = []
                for row in body["branches"]:
                    if isinstance(row, dict):
                        row = dict(row)
                        for key in ("action", "otherwise"):
                            if row.get(key) in mapping:
                                row[key] = mapping[row[key]]
                    branches.append(row)
                body["branches"] = branches
        new_nodes[new_id] = body
    data["nodes"] = new_nodes
    for key in ("root",):
        if data.get(key) in mapping:
            data[key] = mapping[data[key]]
    return mapping


def _rename_inputs(data: dict) -> dict[str, str]:
    inputs = data.get("inputs")
    if not isinstance(inputs, dict):
        return {}
    used = {str(k) for k in inputs if ASCII.fullmatch(str(k))}
    mapping: dict[str, str] = {}
    for i, name in enumerate(inputs, 1):
        if not ASCII.fullmatch(str(name)):
            mapping[str(name)] = _unique(f"input{i}", used)
    if not mapping:
        return {}
    data["inputs"] = {mapping.get(str(k), str(k)): v for k, v in inputs.items()}
    return mapping


def _infer_output_types(data: dict) -> dict[str, str]:
    types: dict[str, str] = {}
    nodes = data.get("nodes")
    if isinstance(nodes, dict):
        for body in nodes.values():
            if not isinstance(body, dict):
                continue
            if isinstance(body.get("returns"), dict):
                types.update({str(k): str(v) for k, v in body["returns"].items()})
            if body.get("type") == "Define" and isinstance(body.get("vars"), dict):
                for name, spec in body["vars"].items():
                    if isinstance(spec, dict) and spec.get("type"):
                        types[str(name)] = str(spec["type"])
            for value in body.values():
                if isinstance(value, str):
                    for m in NEW_PARAM.finditer(value):
                        if m.group(2):
                            types[m.group(1)] = m.group(2)
    return types


def _rename_outputs(data: dict) -> dict[str, str]:
    had_outputs = "outputs" in data
    raw = data.get("outputs")
    inferred = _infer_output_types(data)
    if isinstance(raw, list):
        raw = {str(name): inferred.get(str(name), "object") for name in raw}
    if not isinstance(raw, dict):
        raw = {}
    mapping: dict[str, str] = {}
    used = {str(k) for k in raw if ASCII.fullmatch(str(k))}
    for i, name in enumerate(raw, 1):
        if not ASCII.fullmatch(str(name)):
            mapping[str(name)] = _unique(f"output{i}", used)
    if not raw and not had_outputs:
        data.pop("outputs", None)
        return mapping
    data["outputs"] = {}
    for k, v in raw.items():
        typ = (
            v
            if isinstance(v, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v)
            else inferred.get(str(k), "object")
        )
        data["outputs"][mapping.get(str(k), str(k))] = typ
    return mapping


def _rename_returns(data: dict, registry: PluginRegistry) -> dict[str, str]:
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        return {}
    mapping: dict[str, str] = {}
    for node_id, body in nodes.items():
        if not isinstance(body, dict) or body.get("type") not in ("ref", "FunctionCall"):
            continue
        returns = body.get("returns")
        if not isinstance(returns, dict):
            continue
        source = {}
        if body.get("type") == "FunctionCall":
            spec = registry.function(str(body.get("function") or ""))
            source = dict(spec.returns) if spec is not None else {}
        rebuilt: dict[str, str] = {}
        for i, (name, typ) in enumerate(returns.items()):
            if ASCII.fullmatch(str(name)):
                rebuilt[str(name)] = str(typ)
                continue
            source_name = list(source)[i] if i < len(source) else f"output{i + 1}"
            new = _unique(f"{node_id}_{source_name}", set(rebuilt))
            mapping[str(name)] = new
            rebuilt[new] = str(typ)
        body["returns"] = rebuilt
    return mapping


def migrate_content(
    content: str, registry: PluginRegistry, resolver: MappingResolver
) -> str:
    data = normalize_document(content)
    _rename_nodes(data)
    input_map = _rename_inputs(data)
    output_map = _rename_outputs(data)
    return_map = _rename_returns(data, registry)
    # 引用改写（本树内）
    for old, new in input_map.items():
        data = _replace_refs(data, {old: new}, "Param")
    for old, new in output_map.items():
        data = _replace_refs(data, {old: new}, "Param")
        data = _replace_refs(data, {old: new}, "NewParam")
    for old, new in return_map.items():
        data = _replace_refs(data, {old: new}, "Param")
    normalize_tree_dict(data, registry=registry, resolver=resolver)
    return dump(data)


def main() -> int:
    db_path = ROOT / "data" / "autobranch.db"
    configure_database(db_path)
    registry = PluginRegistry()
    load_builtin_plugins(registry, ROOT / "autobranch" / "plugins")
    db = session_factory()()
    try:
        trees = db.query(Tree).order_by(Tree.id).all()
        # 第一遍：结构/名称迁移（ref 默认名暂不补）
        migrated: dict[str, str] = {}
        for tree in trees:
            data = normalize_document(tree.content)
            _rename_nodes(data)
            _rename_inputs(data)
            _rename_outputs(data)
            _rename_returns(data, registry)
            migrated[tree.name] = dump(data)
        resolver = MappingResolver(
            {name: DocumentSource(id=name, data=content) for name, content in migrated.items()}
        )
        # 第二遍：补默认接收名/类型
        for tree in trees:
            tree.content = migrate_content(migrated[tree.name], registry, resolver)
            tree.status = STATUS_PUBLISHED
        db.query(Experience).delete()
        db.commit()
        print(f"迁移完成：{len(trees)} 棵行为树；已清空 experiences")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
