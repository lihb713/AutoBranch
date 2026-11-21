"""FunctionCall 节点解析 / 函数引用校验 / 泛型与对象类型（组 3）。"""

from __future__ import annotations

import types

import pytest

from autobranch.parser import parse
from autobranch.parser.models import DocumentSource, FunctionCallNode, SequenceNode
from autobranch.schema.errors import SchemaTypeError
from autobranch.schema.types import check_type, coerce, validate_type_name


class FakeRegistry:
    """mock 插件函数注册表（function(name) → 带 parameters 的规范对象）。"""

    def function(self, name):
        if name == "compute.multiply":
            return types.SimpleNamespace(parameters={"required": ["a", "b"]})
        if name == "compute.divide":
            return types.SimpleNamespace(
                parameters={
                    "required": ["a", "b"],
                    "properties": {"a": {}, "b": {}, "op": {}},
                }
            )
        if name == "browser.semantic_graph":
            return types.SimpleNamespace(
                parameters={"required": ["scope", "lod"]}, user_visible=False
            )
        return None


def _doc(
    function: str = "compute.multiply",
    args: list | None = None,
    returns: dict | None = None,
    kwargs: dict | None = None,
):
    node = {
        "type": "FunctionCall",
        "function": function,
        "args": args or ["a", "b"],
        "returns": returns or {"total": "int"},
    }
    if kwargs is not None:
        node["kwargs"] = kwargs
    return DocumentSource(
        id="t",
        data={
            "tree": "t",
            "inputs": {"session": "generics"},
            "nodes": {
                "r": {"type": "Root", "body": "n1"},
                "n1": node,
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
    assert call.returns == (("total", "int"),)


def test_unknown_function_fails_check():
    result = parse(_doc(function="nope"), None, function_registry=FakeRegistry())
    assert not result.checks.ok
    assert any(i.code.startswith("ref.unknown_function") for i in result.checks.issues)


def test_args_mismatch_fails_check():
    result = parse(_doc(args=["a"]), None, function_registry=FakeRegistry())
    assert not result.checks.ok
    assert any(i.code.startswith("ref.args_mismatch") for i in result.checks.issues)


def test_optional_args_allow_more_than_required():
    result = parse(
        _doc(function="compute.divide", args=["a", "b", "float"]),
        None,
        function_registry=FakeRegistry(),
    )
    assert result.checks.ok
    too_many = parse(
        _doc(function="compute.divide", args=["a", "b", "float", "extra"]),
        None,
        function_registry=FakeRegistry(),
    )
    assert not too_many.checks.ok


def test_named_kwargs_allow_skipping_optional_args():
    result = parse(
        _doc(
            function="compute.divide",
            args=["a"],
            kwargs={"b": "2", "op": "named"},
            returns={"result": "float"},
        ),
        None,
        function_registry=FakeRegistry(),
    )
    assert result.checks.ok
    call = result.tree.root.children[0]
    assert call.kwargs == (("b", "2"), ("op", "named"))


def test_named_kwargs_reject_unknown_and_duplicate():
    unknown = parse(
        _doc(function="compute.divide", args=["a"], kwargs={"nope": "1"}),
        None,
        function_registry=FakeRegistry(),
    )
    assert not unknown.checks.ok
    assert any(i.code.startswith("ref.kwargs_invalid") for i in unknown.checks.issues)

    duplicate = parse(
        _doc(function="compute.divide", args=["a"], kwargs={"a": "1"}),
        None,
        function_registry=FakeRegistry(),
    )
    assert not duplicate.checks.ok


def test_missing_required_arg_rejected():
    result = parse(
        _doc(function="compute.divide", args=["a"], kwargs={}),
        None,
        function_registry=FakeRegistry(),
    )
    assert not result.checks.ok
    assert any(i.code.startswith("ref.args_mismatch") for i in result.checks.issues)


def test_llm_only_function_rejected_for_function_call():
    result = parse(
        _doc(function="browser.semantic_graph", args=["full", "2"]),
        None,
        function_registry=FakeRegistry(),
    )
    assert not result.checks.ok
    assert any(i.code == "ref.function_not_user_visible" for i in result.checks.issues)


def test_without_registry_skips_function_check():
    # 未提供注册表：函数存在性不校验（运行时兜底），仅结构解析
    result = parse(_doc(function="nope"), None)
    assert result.checks.ok


def test_function_call_bare_return_name_accepted():
    """returns 接收名为裸 ASCII 名 → 通过（接收即隐式创建变量）。"""
    result = parse(_doc(returns={"total": "int"}), None, function_registry=FakeRegistry())
    assert result.checks.ok


def test_function_call_newparam_prefix_rejected():
    """returns 键含点号（NewParam.x）→ syntax.invalid_return_name（不接受旧前缀）。"""
    result = parse(_doc(returns={"NewParam.total": "int"}), None, function_registry=FakeRegistry())
    assert not result.checks.ok
    assert any(i.code.startswith("syntax.invalid_return_name") for i in result.checks.issues)


def test_function_call_chinese_return_name_rejected():
    """returns 接收名不支持中文（合计 → syntax.invalid_return_name）。"""
    result = parse(_doc(returns={"合计": "int"}), None, function_registry=FakeRegistry())
    assert not result.checks.ok
    assert any(i.code.startswith("syntax.invalid_return_name") for i in result.checks.issues)


def test_non_ascii_param_name_rejected():
    """描述中 Param./NewParam. 后接非 ASCII 变量名 → syntax.invalid_name。"""
    from autobranch.parser import parse as _parse
    from autobranch.parser.models import DocumentSource as _DS

    doc = _DS(
        id="t",
        data={
            "tree": "t",
            "nodes": {
                "r": {"type": "Root", "body": "n1"},
                "n1": {
                    "type": "Action",
                    "description": "提取到 NewParam.苹果金额:int",
                },
            },
            "root": "r",
        },
    )
    result = _parse(doc, None)
    assert not result.checks.ok
    assert any(i.code == "syntax.invalid_name" for i in result.checks.issues)


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
    assert result.decl_inputs == {"session": "generics"}
    assert result.checks.ok


def test_object_type_coerce_and_check():
    validate_type_name("object")
    assert coerce("object", '{"host": "x"}') == {"host": "x"}
    check_type("object", {"host": "x"})
    with pytest.raises(SchemaTypeError):
        check_type("object", "任何值")


def test_generics_type_accepts_any_value():
    validate_type_name("generics")
    page = types.SimpleNamespace(id="p1", url="http://x")
    assert coerce("generics", page) is page
    check_type("generics", page)
    check_type("generics", "任何值")
