"""行为树文档命令应用（后端权威编辑）。

命令只修改原始 YAML dict；默认名/类型由 ``normalize`` 服务补全。
前端不计算节点 id、Step 子节点、删除/槽位语义。
"""

from __future__ import annotations

from typing import Any

import yaml

from autobranch.parser.yamlio import normalize_document
from autobranch.server.errors import AppError
from autobranch.server.schemas.tree import TreeCommand
from autobranch.server.services.normalize import normalize_tree_dict

NODE_TYPES = {
    "Action",
    "Step",
    "Root",
    "Sequence",
    "IfThenElse",
    "Branch",
    "Retry",
    "LoopUntil",
    "ref",
    "FunctionCall",
    "Define",
}

_SLOT_KEYS = ("body", "actions", "action", "then", "else", "branches")


def load(data: str | dict) -> dict[str, Any]:
    return normalize_document(data)


def dump(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


def empty_document(tree_name: str) -> str:
    """空树文档（仅 Root 节点）。"""
    return dump(
        {
            "tree": tree_name,
            "nodes": {"n1": {"type": "Root", "name": "根"}},
            "root": "n1",
        }
    )


def _nodes(data: dict[str, Any]) -> dict[str, Any]:
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        raise AppError(422, "行为树文档缺少 nodes")
    return nodes


def next_node_id(nodes: dict[str, Any]) -> str:
    i = 1
    while f"n{i}" in nodes:
        i += 1
    return f"n{i}"


def make_node(node_type: str, node_id: str) -> dict[str, Any]:
    if node_type not in NODE_TYPES:
        raise AppError(422, f"未知节点类型: {node_type}")
    body: dict[str, Any] = {"type": node_type, "name": node_type}
    if node_type == "ref":
        body.update({"target": "", "args": [], "returns": {}})
    elif node_type == "FunctionCall":
        body.update({"function": "", "args": [], "returns": {}})
    elif node_type == "Define":
        body["vars"] = {}
    elif node_type == "Sequence":
        body["actions"] = []
    elif node_type == "Branch":
        body["branches"] = []
    return body


def slot_mounts(body: dict[str, Any]) -> list[tuple[str, Any]]:
    """返回全部挂载点（含空槽位，供 set_slot/detach_slot 用）。

    ('body'|'action'|'then'|'else', child_or_None) 或 ('actions'|'branches', row)。
    """
    kind = body.get("type")
    if kind == "Root":
        return [("body", body.get("body"))]
    if kind in ("Step", "Retry", "LoopUntil"):
        return [("action", body.get("action"))]
    if kind == "IfThenElse":
        return [("then", body.get("then")), ("else", body.get("else"))]
    if kind == "Sequence":
        return [("actions", c) for c in (body.get("actions") or [])]
    if kind == "Branch":
        out: list[tuple[str, Any]] = [("action", body.get("action"))]
        out.extend(("branches", row) for row in (body.get("branches") or []))
        return out
    return []


def slot_children(body: dict[str, Any]) -> list[tuple[str, Any]]:
    """返回已挂载子节点（删除/遍历用）：('field', child_id) 或 ('branches', row)。"""
    out: list[tuple[str, Any]] = []
    for field, value in slot_mounts(body):
        if field == "branches":
            if isinstance(value, dict) and (value.get("action") or value.get("otherwise")):
                out.append((field, value))
        elif value:
            out.append((field, value))
    return out


def _all_child_ids(body: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for field, value in slot_children(body):
        if field == "branches":
            cid = value.get("action") or value.get("otherwise")
        else:
            cid = value
        if isinstance(cid, str) and cid:
            ids.append(cid)
    return ids


def _remove_references(nodes: dict[str, Any], gone: set[str]) -> None:
    for body in nodes.values():
        if not isinstance(body, dict):
            continue
        for key in ("body", "action", "then", "else"):
            if body.get(key) in gone:
                body.pop(key, None)
        if isinstance(body.get("actions"), list):
            body["actions"] = [c for c in body["actions"] if c not in gone]
        branches = body.get("branches")
        if isinstance(branches, list):
            kept: list[Any] = []
            for row in branches:
                if isinstance(row, dict) and (row.get("action") or row.get("otherwise")) in gone:
                    continue
                kept.append(row)
            body["branches"] = kept


def _delete_node(data: dict[str, Any], node_id: str, subtree: bool) -> None:
    nodes = _nodes(data)
    if data.get("root") == node_id:
        raise AppError(422, "根节点不可删除")
    if node_id not in nodes:
        raise AppError(404, f"节点不存在: {node_id}")
    if subtree:
        doomed: set[str] = set()
        stack = [node_id]
        while stack:
            nid = stack.pop()
            if nid in doomed:
                continue
            doomed.add(nid)
            body = nodes.get(nid)
            if isinstance(body, dict):
                stack.extend(_all_child_ids(body))
        _remove_references(nodes, doomed)
        for nid in doomed:
            nodes.pop(nid, None)
    else:
        _remove_references(nodes, {node_id})
        nodes.pop(node_id, None)


def _with_old_defaults_cleared(
    node_id: str,
    body: dict[str, Any],
    old_source: dict[str, str],
    patch: dict[str, Any],
) -> None:
    """函数/目标切换：清空仍等于旧默认名的接收名，交给归一化重算。"""
    if not old_source:
        return
    returns = body.get("returns")
    if not isinstance(returns, dict):
        return
    new_patch_returns = patch.get("returns")
    if isinstance(new_patch_returns, dict):
        return  # 前端显式提交名称：按用户输入处理
    old_defaults = {f"{node_id}_{name}" for name in old_source}
    rebuilt: dict[str, Any] = {}
    for i, (key, value) in enumerate(list(returns.items())):
        if i < len(old_source) and key in old_defaults:
            rebuilt[f"\x00auto{i}"] = value  # 占位 → 归一化按新来源生成
        else:
            rebuilt[key] = value
    body["returns"] = rebuilt


def _update_node(
    data: dict[str, Any],
    node_id: str,
    patch: dict[str, Any],
    registry: Any,
    resolver: Any,
) -> None:
    nodes = _nodes(data)
    body = nodes.get(node_id)
    if not isinstance(body, dict):
        raise AppError(404, f"节点不存在: {node_id}")
    if "id" in patch or "type" in patch:
        raise AppError(422, "节点 id/type 不可通过 update_node 修改")
    old_source: dict[str, str] = {}
    if body.get("type") == "FunctionCall" and "function" in patch:
        old_fn = body.get("function")
        old_spec = registry.function(old_fn) if registry is not None and old_fn else None
        old_source = dict(old_spec.returns) if old_spec is not None else {}
    elif body.get("type") == "ref" and "target" in patch:
        old_source = _ref_outputs(body.get("target"), resolver)
    if old_source:
        _with_old_defaults_cleared(node_id, body, old_source, patch)
    for key, value in patch.items():
        if key in ("id", "type"):
            continue
        if value is None:
            body.pop(key, None)
        else:
            body[key] = value


def _set_slot(
    data: dict[str, Any], node_id: str, slot_index: int, child_id: str | None
) -> None:
    nodes = _nodes(data)
    body = nodes.get(node_id)
    if not isinstance(body, dict):
        raise AppError(404, f"节点不存在: {node_id}")
    mounts = slot_mounts(body)
    if slot_index < 0 or slot_index >= len(mounts):
        raise AppError(422, f"槽位序号非法: {slot_index}")
    field, value = mounts[slot_index]
    if field == "branches":
        row = value
        if child_id:
            row["action"] = child_id
            row.pop("otherwise", None)
        else:
            branches = body.get("branches") or []
            body["branches"] = [r for r in branches if r is not row]
        return
    if child_id:
        if field == "actions":
            actions = list(body.get("actions") or [])
            actions[slot_index] = child_id
            body["actions"] = actions
        else:
            body[field] = child_id
        return
    if field == "actions":
        actions = list(body.get("actions") or [])
        actions.pop(slot_index)
        body["actions"] = actions
    else:
        body.pop(field, None)


def _ref_outputs(target: Any, resolver: Any) -> dict[str, str]:
    if not isinstance(target, str) or not target.strip() or resolver is None:
        return {}
    try:
        src = resolver.resolve(target.strip())
        raw = normalize_document(src.data)
    except Exception:  # noqa: BLE001
        return {}
    outputs = raw.get("outputs")
    return {str(k): str(v) for k, v in outputs.items()} if isinstance(outputs, dict) else {}


def apply_commands(
    content: str,
    commands: list[TreeCommand],
    *,
    registry: Any,
    resolver: Any,
) -> tuple[str, str | None, str | None]:
    """应用命令并归一化。

    :return: ``(新文档文本, 新建节点 id, 新树名/None)``
    """
    data = load(content)
    created_id: str | None = None
    new_tree_name: str | None = None
    for cmd in commands:
        if cmd.op == "add_node":
            if not cmd.node_type:
                raise AppError(422, "add_node 缺少 node_type")
            nodes = _nodes(data)
            node_id = next_node_id(nodes)
            nodes[node_id] = make_node(cmd.node_type, node_id)
            created_id = node_id
            if cmd.node_type == "Step":
                action_id = next_node_id(nodes)
                nodes[action_id] = make_node("Action", action_id)
                nodes[action_id]["name"] = "操作"
                nodes[node_id]["action"] = action_id
        elif cmd.op == "delete_node":
            if not cmd.node_id:
                raise AppError(422, "delete_node 缺少 node_id")
            _delete_node(data, cmd.node_id, cmd.subtree)
        elif cmd.op == "update_node":
            if not cmd.node_id or not isinstance(cmd.patch, dict):
                raise AppError(422, "update_node 需要 node_id 与 patch")
            _update_node(data, cmd.node_id, cmd.patch, registry, resolver)
        elif cmd.op in ("set_slot", "detach_slot"):
            if not cmd.node_id or cmd.slot_index is None:
                raise AppError(422, f"{cmd.op} 需要 node_id 与 slot_index")
            _set_slot(
                data,
                cmd.node_id,
                cmd.slot_index,
                None if cmd.op == "detach_slot" else (cmd.child_id or ""),
            )
        elif cmd.op == "update_doc":
            patch = cmd.patch or {}
            if "tree" in patch and isinstance(patch["tree"], str):
                new_tree_name = patch["tree"].strip()
                data["tree"] = new_tree_name
            for key in ("inputs", "outputs", "config"):
                if key in patch:
                    data[key] = patch[key]
        else:  # pragma: no cover - Literal 已限制
            raise AppError(422, f"未知命令: {cmd.op}")
    normalize_tree_dict(data, registry=registry, resolver=resolver)
    return dump(data), created_id, new_tree_name


__all__ = [
    "NODE_TYPES",
    "empty_document",
    "load",
    "dump",
    "apply_commands",
    "next_node_id",
    "make_node",
]
