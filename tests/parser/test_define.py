"""Define 节点解析与校验（变量声明）。"""

from __future__ import annotations

from autobranch.parser import parse
from autobranch.parser.models import DocumentSource


def _doc(vars_: dict, extra_nodes: dict | None = None) -> DocumentSource:
    nodes = {
        "n1": {"type": "Root", "body": "s1"},
        "s1": {"type": "Sequence", "actions": ["d1"]},
        "d1": {"type": "Define", "vars": vars_},
    }
    if extra_nodes:
        nodes.update(extra_nodes)
        nodes["s1"]["actions"] = ["d1", *extra_nodes]
    return DocumentSource(id="t", data={"tree": "t", "root": "n1", "nodes": nodes})


def _find(node, name: str):
    if node.__class__.__name__ == name:
        return node
    for child in getattr(node, "children", ()) or ():
        found = _find(child, name)
        if found is not None:
            return found
    return None


def test_parse_define_ok() -> None:
    result = parse(
        _doc({"a": {"type": "str", "value": "x"}, "b": {"type": "int", "value": "2"}}),
        None,
    )
    assert result.checks.ok, result.checks.issues
    node = _find(result.tree.root, "DefineNode")
    assert node is not None
    assert node.vars == (("a", "str", "x"), ("b", "int", "2"))


def test_define_arbitrary_var_count() -> None:
    vars_ = {f"v{i}": {"type": "int", "value": str(i)} for i in range(5)}
    result = parse(_doc(vars_), None)
    assert result.checks.ok, result.checks.issues


def test_define_invalid_name() -> None:
    result = parse(_doc({"合计": {"type": "str", "value": "x"}}), None)
    assert any(i.code == "syntax.invalid_name" for i in result.checks.issues)


def test_define_invalid_type() -> None:
    result = parse(_doc({"a": {"type": "bogus", "value": "x"}}), None)
    assert not result.checks.ok
    assert any("非法" in i.message for i in result.checks.issues)


def test_define_undefined_param_value() -> None:
    result = parse(_doc({"a": {"type": "str", "value": "Param.nope"}}), None)
    assert any(i.code == "scope.get_undeclared" for i in result.checks.issues)


def test_define_var_defined_for_later_param_read() -> None:
    result = parse(
        _doc(
            {"token": {"type": "str", "value": "abc"}},
            {"a1": {"type": "Action", "description": "使用 Param.token 登录"}},
        ),
        None,
    )
    assert result.checks.ok, result.checks.issues


def test_define_value_param_copy_ok() -> None:
    result = parse(
        _doc(
            {
                "orig": {"type": "str", "value": "hello"},
                "alias": {"type": "str", "value": "Param.orig"},
            }
        ),
        None,
    )
    assert result.checks.ok, result.checks.issues


def test_define_missing_or_empty_vars_rejected() -> None:
    doc = DocumentSource(
        id="t",
        data={
            "tree": "t",
            "root": "n1",
            "nodes": {
                "n1": {"type": "Root", "body": "d1"},
                "d1": {"type": "Define", "vars": {}},
            },
        },
    )
    result = parse(doc, None)
    assert not result.checks.ok
