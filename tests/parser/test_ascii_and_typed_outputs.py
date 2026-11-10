"""参数名/节点 id ASCII + outputs 带类型映射（默认接收名变更）。"""

from __future__ import annotations

from autobranch.parser import parse
from autobranch.parser.models import DocumentSource
from autobranch.parser.refs import MappingResolver


def _doc(**overrides):
    data = {
        "tree": "t",
        "nodes": {
            "n1": {"type": "Root", "body": "n2"},
            "n2": {"type": "Action", "description": "x"},
        },
        "root": "n1",
    }
    data.update(overrides)
    return DocumentSource(id="t", data=data)


def test_ascii_node_id_required():
    result = parse(
        _doc(nodes={"节点1": {"type": "Root"}}, root="节点1"),
        MappingResolver(),
    )
    assert not result.checks.ok
    assert any(i.code == "syntax.invalid_name" for i in result.checks.issues)


def test_ascii_inputs_required():
    result = parse(_doc(inputs={"账号": "str"}), MappingResolver())
    assert not result.checks.ok
    assert any(i.code == "syntax.invalid_name" for i in result.checks.issues)


def test_outputs_must_be_typed_mapping():
    result = parse(_doc(outputs={"结果": "str"}), MappingResolver())
    assert not result.checks.ok
    assert any(i.code == "syntax.invalid_name" for i in result.checks.issues)
    assert result.decl_outputs == {"结果": "str"}


def test_legacy_outputs_list_rejected():
    result = parse(_doc(outputs=["result"]), MappingResolver())
    assert not result.checks.ok
    assert any(i.code == "structure.invalid_decl" for i in result.checks.issues)


def test_outputs_invalid_type_rejected():
    result = parse(_doc(outputs={"result": "unknown"}), MappingResolver())
    assert not result.checks.ok
    assert any(i.code == "structure.invalid_decl" for i in result.checks.issues)


def test_ref_returns_type_must_match_target_outputs():
    child = DocumentSource(
        id="child",
        data={
            "tree": "child",
            "outputs": {"result": "str"},
            "nodes": {
                "n1": {"type": "Root", "body": "n2"},
                "n2": {"type": "Action", "description": "x"},
            },
            "root": "n1",
        },
    )
    resolver = MappingResolver({"child": child})
    parent = DocumentSource(
        id="parent",
        data={
            "tree": "parent",
            "nodes": {
                "n1": {"type": "Root", "body": "n2"},
                "n2": {
                    "type": "ref",
                    "target": "child",
                    "args": [],
                    "returns": {"myResult": "int"},
                },
            },
            "root": "n1",
        },
    )
    result = parse(parent, resolver)
    assert not result.checks.ok
    assert any(i.code == "ref.type_mismatch" for i in result.checks.issues)
