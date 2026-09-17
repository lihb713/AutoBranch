"""FunctionCall 节点解析 / 函数引用校验 / 泛型 object 类型（组 3）。"""

from __future__ import annotations

import types

from autobranch.parser import parse
from autobranch.parser.models import DocumentSource, FunctionCallNode, SequenceNode
from autobranch.schema.types import check_type, coerce, validate_type_name


class FakeRegistry:
    """mock 插件函数注册表（function(name) → 带 parameters 的规范对象）。"""

    def function(self, name):
        if name == "compute.multiply":
            return types.SimpleNamespace(parameters={"required": ["a", "b"]})
        return None


def _doc(function: str = "compute.multiply", args: list | None = None, returns: dict | None = None):
    return DocumentSource(
        id="t",
        data={
            "tree": "t",
            "inputs": {"会话": "object"},
            "nodes": {
                "r": {"type": "Root", "body": "n1"},
                "n1": {
                    "type": "FunctionCall",
                    "function": function,
                    "args": args or ["a", "b"],
                    "returns": returns or {"结果": "int"},
                },
            },
            "root": "r",
        },
    )


def test_valid_function_call_parses():
    result = parse(_doc(), None, function_registry=FakeRegistry())
    assert result.checks.ok
    root = result.tree.root
    assert isinstance(root, SequenceNode)
    call = root.children[0]
    assert isinstance(call, FunctionCallNode)
    assert call.function == "compute.multiply"
    assert call.args == ("a", "b")
    assert call.returns == (("结果", "int"),)


def test_unknown_function_fails_check():
    result = parse(_doc(function="nope"), None, function_registry=FakeRegistry())
    assert not result.checks.ok
    assert any(i.code.startswith("ref.unknown_function") for i in result.checks.issues)


def test_args_mismatch_fails_check():
    result = parse(_doc(args=["a"]), None, function_registry=FakeRegistry())
    assert not result.checks.ok
    assert any(i.code.startswith("ref.args_mismatch") for i in result.checks.issues)


def test_without_registry_skips_function_check():
    # 未提供注册表：函数存在性不校验（运行时兜底），仅结构解析
    result = parse(_doc(function="nope"), None)
    assert result.checks.ok


def test_function_call_missing_function_field():
    doc = DocumentSource(
        id="t",
        data={
            "tree": "t",
            "nodes": {"r": {"type": "Root", "body": "n1"}, "n1": {"type": "FunctionCall"}},
            "root": "r",
        },
    )
    result = parse(doc, None)
    assert not result.checks.ok
    assert any(i.code.startswith("structure.missing_field") for i in result.checks.issues)


def test_object_type_token_declared():
    result = parse(_doc(), None, function_registry=FakeRegistry())
    assert result.decl_inputs == {"会话": "object"}
    assert result.checks.ok


def test_object_type_coerce_and_check():
    validate_type_name("object")
    page = types.SimpleNamespace(id="p1", url="http://x")
    assert coerce("object", page) is page
    check_type("object", page)
    check_type("object", "任何值")
    assert coerce("object", "str 也原样")
