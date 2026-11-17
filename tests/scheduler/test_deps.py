"""M10 依赖图与循环检测单元测试。"""

from __future__ import annotations

from types import SimpleNamespace

from autobranch.scheduler.deps import build_dependency_graph, detect_cycle


def rule(rule_id: int, target: int, deps: list[int]) -> SimpleNamespace:
    return SimpleNamespace(id=rule_id, target_tree_id=target, dependencies=deps)


def test_build_graph_unions_rules_for_same_target() -> None:
    graph = build_dependency_graph([rule(1, 10, [20]), rule(2, 10, [30])])
    assert graph[10] == {20, 30}


def test_detect_cycle_direct_and_indirect() -> None:
    rules = [rule(1, 1, [2]), rule(2, 2, [1])]
    assert detect_cycle(1, [2], rules, exclude_rule_id=1) is True

    rules = [rule(1, 1, [2]), rule(2, 2, [3]), rule(3, 3, [2])]
    assert detect_cycle(1, [2], rules, exclude_rule_id=1) is True


def test_no_cycle_is_allowed() -> None:
    rules = [rule(1, 1, [2]), rule(2, 2, [])]
    assert detect_cycle(1, [2], rules, exclude_rule_id=1) is False


def test_self_dependency_is_cycle() -> None:
    assert detect_cycle(1, [1], []) is True
