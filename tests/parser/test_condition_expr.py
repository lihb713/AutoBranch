"""条件模式与谓词表达式解析/校验。"""

from __future__ import annotations

from pathlib import Path

from autobranch.parser import parse
from autobranch.parser.models import DocumentSource
from autobranch.plugin_system import PluginRegistry, load_builtin_plugins


def _registry() -> PluginRegistry:
    reg = PluginRegistry()
    load_builtin_plugins(reg, Path("autobranch/plugins"))
    return reg


def _doc(condition: object) -> DocumentSource:
    return DocumentSource(
        id="t",
        data={
            "tree": "t",
            "inputs": {"amount": "int"},
            "nodes": {
                "r": {"type": "Root", "body": "n2"},
                "n2": {"type": "IfThenElse", "if": condition, "then": "n3", "else": "n4"},
                "n3": {"type": "Action", "description": "x"},
                "n4": {"type": "Action", "description": "y"},
            },
            "root": "r",
        },
    )


def test_predicate_condition_parses():
    result = parse(
        _doc(
            {
                "mode": "predicate",
                "expression": {
                    "all": [
                        {"function": "predicate.gt", "args": ["Param.amount", "0"]},
                        {
                            "any": [
                                {"function": "predicate.eq", "args": ["a", "b"]},
                                {"not": {"function": "predicate.is_empty", "args": [""]}},
                            ]
                        },
                    ]
                },
            }
        ),
        None,
        function_registry=_registry(),
    )
    assert result.checks.ok, result.checks.issues


def test_predicate_condition_empty_group_rejected():
    result = parse(
        _doc({"mode": "predicate", "expression": {"all": []}}),
        None,
        function_registry=_registry(),
    )
    assert not result.checks.ok
    assert any(i.code.endswith("invalid_expression") for i in result.checks.issues)


def test_predicate_condition_requires_bool_return():
    result = parse(
        _doc(
            {
                "mode": "predicate",
                "expression": {"function": "compute.add", "args": ["1", "2"]},
            }
        ),
        None,
        function_registry=_registry(),
    )
    assert not result.checks.ok
    assert any(i.code.endswith("not_boolean") for i in result.checks.issues)


def test_natural_condition_must_be_single_line():
    result = parse(
        _doc({"mode": "natural", "text": "第一行\n第二行"}),
        None,
        function_registry=_registry(),
    )
    assert not result.checks.ok
    assert any(i.code.endswith("invalid_value") for i in result.checks.issues)


def test_bare_string_is_natural_condition():
    result = parse(_doc("出现成功"), None, function_registry=_registry())
    assert result.checks.ok, result.checks.issues
