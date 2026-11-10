"""后端文档归一化（默认接收名 / 类型 / 冲突后缀）。

单一实现，供草稿命令、保存、迁移与运行前兜底复用：

- ``FunctionCall``：按插件函数 ``returns`` 补接收名与类型；
- ``ref``：按目标文档 ``outputs`` 补接收名与类型；
- 名称格式 ``<节点id>_<返回参数名>``；冲突只对自动名追加 ``_1/_2``；
- 用户已有名称保留；数量多于来源声明时截断；
- 类型永远取来源声明，用户不可编辑；
- **不**改写文档内 ``Param.<旧名>`` 引用（由保存校验发现）。
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml

from autobranch.parser.refs import RefResolver
from autobranch.parser.yamlio import normalize_document

#: 变量声明写入语法（Action 描述中的 NewParam.<名>）。
_NEW_PARAM = re.compile(r"(?<![A-Za-z0-9_])NewParam\.([A-Za-z_][A-Za-z0-9_]*)")


def _unique_name(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    i = 1
    while f"{base}_{i}" in used:
        i += 1
    return f"{base}_{i}"


def _collect_used_vars(data: dict[str, Any]) -> set[str]:
    """收集本帧已声明变量：inputs/outputs/Define/returns/Action NewParam。"""
    used: set[str] = set()
    inputs = data.get("inputs")
    if isinstance(inputs, dict):
        used.update(str(k) for k in inputs)
    outputs = data.get("outputs")
    if isinstance(outputs, dict):
        used.update(str(k) for k in outputs)
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        return used
    for body in nodes.values():
        if not isinstance(body, dict):
            continue
        if body.get("type") in ("ref", "FunctionCall"):
            returns = body.get("returns")
            if isinstance(returns, dict):
                used.update(str(k) for k in returns)
        elif body.get("type") == "Define":
            variables = body.get("vars")
            if isinstance(variables, dict):
                used.update(str(k) for k in variables)
        else:
            for value in body.values():
                if isinstance(value, str):
                    used.update(_NEW_PARAM.findall(value))
    return used


def _source_returns(
    body: dict[str, Any],
    registry: Any,
    resolver: RefResolver | None,
) -> dict[str, str]:
    """返回该节点来源声明的 (返回参数名 → 类型) 映射（按声明顺序）。"""
    kind = body.get("type")
    if kind == "FunctionCall":
        function = body.get("function")
        if not isinstance(function, str) or not function.strip():
            return {}
        spec = registry.function(function) if registry is not None else None
        return dict(spec.returns) if spec is not None else {}
    if kind == "ref":
        target = body.get("target")
        if not isinstance(target, str) or not target.strip() or resolver is None:
            return {}
        try:
            source = resolver.resolve(target.strip())
        except Exception:  # noqa: BLE001 - 目标不存在/非正式版：不补名，交给校验
            return {}
        try:
            raw = normalize_document(source.data)
        except Exception:  # noqa: BLE001
            return {}
        outputs = raw.get("outputs")
        if not isinstance(outputs, dict):
            return {}
        return {str(k): str(v) for k, v in outputs.items()}
    return {}


def _normalize_returns(
    data: dict[str, Any],
    registry: Any,
    resolver: RefResolver | None,
) -> None:
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        return
    used = _collect_used_vars(data)
    # 先移除当前节点已有名对自动冲突判断的影响：逐个节点处理时，
    # used 仍包含其已有名（用户显式名不应被自动改名，但自动名不得与之冲突）。
    for node_id, body in nodes.items():
        if not isinstance(body, dict) or body.get("type") not in ("ref", "FunctionCall"):
            continue
        source = _source_returns(body, registry, resolver)
        existing = body.get("returns")
        existing_items = list(existing.items()) if isinstance(existing, dict) else []
        # 当前节点已有名先保留在 used 中；自动名生成时避开它们。
        new_returns: dict[str, str] = {}
        for i, (ret_name, ret_type) in enumerate(source.items()):
            existing_name = str(existing_items[i][0]).strip() if i < len(existing_items) else ""
            is_auto = not existing_name or existing_name.startswith("\x00auto")
            if existing_name and not is_auto:
                name = existing_name
            else:
                base = f"{node_id}_{ret_name}"
                name = _unique_name(base, used | set(new_returns))
            new_returns[name] = str(ret_type)
            used.add(name)
        body["returns"] = new_returns


def normalize_tree_dict(
    data: dict[str, Any],
    *,
    registry: Any,
    resolver: RefResolver | None = None,
) -> dict[str, Any]:
    """原地归一化文档 dict（补默认接收名/类型），返回同一 dict。"""
    _normalize_returns(data, registry, resolver)
    return data


def normalize_tree_content(
    content: str,
    *,
    registry: Any,
    resolver: RefResolver | None = None,
) -> str:
    """归一化 YAML 文档文本并重新序列化（保留键顺序与中文）。"""
    data = normalize_document(content)
    original = copy.deepcopy(data)
    normalize_tree_dict(data, registry=registry, resolver=resolver)
    if data == original:
        return content
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


def normalize_tree_file(
    path: str | Path,
    *,
    registry: Any,
    resolver: RefResolver | None = None,
) -> str:
    """读取文件并归一化（迁移脚本便捷入口）。"""
    return normalize_tree_content(
        Path(path).read_text(encoding="utf-8"), registry=registry, resolver=resolver
    )


__all__ = [
    "normalize_tree_dict",
    "normalize_tree_content",
    "normalize_tree_file",
]
