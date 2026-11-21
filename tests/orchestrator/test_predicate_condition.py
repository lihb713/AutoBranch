"""谓词条件执行：短路、错误不等于 false、报告。"""

from __future__ import annotations

from pathlib import Path

from orchestrator_helpers import make_run_context

from autobranch.orchestrator import FAILURE, SUCCESS
from autobranch.orchestrator.traverser import Traverser
from autobranch.parser.models import (
    BranchSpec,
    ConditionNode,
    PredicateCall,
    PredicateGroup,
    SelectorNode,
    SequenceNode,
)
from autobranch.plugin_system import PluginRegistry, load_builtin_plugins


def _registry() -> PluginRegistry:
    reg = PluginRegistry()
    load_builtin_plugins(reg, Path("autobranch/plugins"))
    return reg


def _pred(*args, function="predicate.eq", **kwargs):
    return PredicateCall(function=function, args=tuple(args), kwargs=tuple(kwargs.items()))


def test_predicate_condition_true_false_and_report(config):
    ctx = make_run_context(config)
    ctx.registry = _registry()
    node = ConditionNode(
        mode="predicate",
        expression=PredicateGroup(op="all", children=(_pred("1", "1"), _pred("2", "2"))),
    )
    assert Traverser(ctx).tick(node) == SUCCESS
    report = ctx.reporter.exec_state().completed[-1]
    assert report.condition_result is True
    assert report.details["最终结果"] is True

    ctx2 = make_run_context(config)
    ctx2.registry = _registry()
    node2 = ConditionNode(mode="predicate", expression=_pred("1", "2"))
    assert Traverser(ctx2).tick(node2) == FAILURE
    assert ctx2.reporter.exec_state().completed[-1].condition_result is False


def test_predicate_short_circuits_before_error(config):
    ctx = make_run_context(config)
    ctx.registry = _registry()
    node = ConditionNode(
        mode="predicate",
        expression=PredicateGroup(
            op="all",
            children=(
                _pred("1", "2"),
                _pred("not-a-number", "1", function="predicate.gt"),
            ),
        ),
    )
    assert Traverser(ctx).tick(node) == FAILURE
    assert ctx.failure_reason is None
    assert ctx.reporter.exec_state().completed[-1].condition_result is False


def test_predicate_error_aborts_selector_instead_of_fallback(config):
    ctx = make_run_context(config)
    ctx.registry = _registry()
    error_cond = ConditionNode(
        mode="predicate", expression=_pred("not-a-number", "1", function="predicate.gt")
    )
    selector = SelectorNode(
        branches=(
            BranchSpec(condition=error_cond, child=SequenceNode()),
            BranchSpec(condition=None, child=SequenceNode()),
        )
    )
    assert Traverser(ctx).tick(selector) == FAILURE
    assert ctx.failure_reason is not None
    assert "predicate.gt" in ctx.failure_reason
