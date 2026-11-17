"""M10 前置依赖图与循环检测。

依赖语义是“行为树级别”的：规则的目标树 → 依赖的行为树列表。同一棵树可能被
多条规则指向，构建图时取并集。配置依赖时用 DFS 从目标树出发，若能回到目标
树自身则判定为环。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def build_dependency_graph(
    rules: Iterable[Any], *, exclude_rule_id: int | None = None
) -> dict[int, set[int]]:
    """把规则集合聚合为 ``tree_id -> 依赖树 id 集合``。"""
    graph: dict[int, set[int]] = {}
    for rule in rules:
        if exclude_rule_id is not None and getattr(rule, "id", None) == exclude_rule_id:
            continue
        target = getattr(rule, "target_tree_id", None)
        if target is None:
            continue
        deps = {int(item) for item in (getattr(rule, "dependencies", None) or [])}
        graph.setdefault(int(target), set()).update(deps)
    return graph


def detect_cycle(
    target_tree_id: int,
    dependencies: Iterable[int],
    rules: Iterable[Any],
    *,
    exclude_rule_id: int | None = None,
) -> bool:
    """从目标树出发沿依赖图 DFS；能回到目标树则存在环。"""
    graph = build_dependency_graph(rules, exclude_rule_id=exclude_rule_id)
    graph.setdefault(int(target_tree_id), set()).update(int(dep) for dep in dependencies)

    target = int(target_tree_id)
    visiting: set[int] = set()
    visited: set[int] = set()

    def dfs(tree_id: int) -> bool:
        if tree_id == target:
            return True
        if tree_id in visiting:
            return True
        if tree_id in visited:
            return False
        visiting.add(tree_id)
        for dep in graph.get(tree_id, set()):
            if dep == target or dfs(dep):
                return True
        visiting.discard(tree_id)
        visited.add(tree_id)
        return False

    for dep in graph.get(target, set()):
        if dep == target or dfs(dep):
            return True
    return False


def dependency_chain(
    tree_id: int, rules: Iterable[Any], *, _seen: set[int] | None = None
) -> set[int]:
    """返回某棵树全部递归依赖（用于诊断/测试；环已由配置校验拦截）。"""
    seen = _seen if _seen is not None else set()
    if tree_id in seen:
        return seen
    seen.add(tree_id)
    graph = build_dependency_graph(rules)
    for dep in graph.get(tree_id, set()):
        dependency_chain(dep, rules, _seen=seen)
    return seen


__all__ = ["build_dependency_graph", "detect_cycle", "dependency_chain"]
