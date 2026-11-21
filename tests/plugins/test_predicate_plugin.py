"""predicate 插件：常用单 bool 谓词函数。"""

from __future__ import annotations

from autobranch.plugin_system import PluginRegistry
from autobranch.plugins.predicate import PredicatePlugin


def _registry() -> PluginRegistry:
    reg = PluginRegistry()
    reg.register(PredicatePlugin())
    return reg


def test_predicate_comparisons():
    reg = _registry()
    assert reg.call("predicate.eq", {"a": 1, "b": 1}).value is True
    assert reg.call("predicate.ne", {"a": 1, "b": 2}).value is True
    assert reg.call("predicate.gt", {"a": 2, "b": 1}).value is True
    assert reg.call("predicate.ge", {"a": 2, "b": 2}).value is True
    assert reg.call("predicate.lt", {"a": 1, "b": 2}).value is True
    assert reg.call("predicate.le", {"a": 2, "b": 2}).value is True
    assert reg.call("predicate.between", {"value": 5, "low": 1, "high": 10}).value is True


def test_predicate_strings():
    reg = _registry()
    assert reg.call("predicate.contains", {"value": "Hello", "needle": "ell"}).value is True
    assert (
        reg.call(
            "predicate.contains",
            {"value": "Hello", "needle": "ELL", "ignore_case": True},
        ).value
        is True
    )
    assert reg.call("predicate.not_contains", {"value": "abc", "needle": "x"}).value is True
    assert reg.call("predicate.starts_with", {"value": "abc", "prefix": "ab"}).value is True
    assert reg.call("predicate.ends_with", {"value": "abc", "suffix": "bc"}).value is True
    assert reg.call("predicate.matches", {"value": "abc", "pattern": "b"}).value is True
    assert reg.call("predicate.matches_full", {"value": "abc", "pattern": "abc"}).value is True


def test_predicate_empty_collection_length():
    reg = _registry()
    for value in (None, "", [], {}):
        assert reg.call("predicate.is_empty", {"value": value}).value is True
        assert reg.call("predicate.is_not_empty", {"value": value}).value is False
    assert reg.call("predicate.is_null", {"value": None}).value is True
    assert reg.call("predicate.is_not_null", {"value": 0}).value is True
    assert reg.call("predicate.has_key", {"data": {"a": 1}, "key": "a"}).value is True
    assert reg.call("predicate.has_value", {"data": {"a": 1}, "value": 1}).value is True
    assert reg.call("predicate.value_in", {"value": "a", "values": ["a", "b"]}).value is True
    assert reg.call("predicate.value_not_in", {"value": "c", "values": ["a", "b"]}).value is True
    assert reg.call("predicate.length_eq", {"value": [1, 2], "n": 2}).value is True
    assert reg.call("predicate.length_gt", {"value": "abc", "n": 2}).value is True


def test_predicate_type_error_is_failure_not_false():
    reg = _registry()
    result = reg.call("predicate.gt", {"a": object(), "b": 1})
    assert result.ok is False
    result = reg.call("predicate.contains", {"value": 1, "needle": "x"})
    assert result.ok is False


def test_predicate_functions_are_single_bool_without_output_param():
    reg = _registry()
    for spec in reg.functions_of("predicate"):
        assert spec.returns == {"result": "bool"}
        assert spec.output_param is None
