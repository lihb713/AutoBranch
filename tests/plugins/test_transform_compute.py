"""transform（数据提取/变换）与 compute 扩展函数测试。"""

from __future__ import annotations

from autobranch.plugin_system import PluginRegistry
from autobranch.plugins.compute import ComputePlugin
from autobranch.plugins.transform import TransformPlugin


def _transform():
    reg = PluginRegistry()
    reg.register(TransformPlugin())
    return reg


def _compute():
    reg = PluginRegistry()
    reg.register(ComputePlugin())
    return reg


def test_transform_append_and_dict_set():
    reg = _transform()
    appended = reg.call(
        "transform.append", {"list_var": '["a"]', "value": {"id": 2}}
    )
    assert appended.ok
    assert appended.value == '["a", {"id": 2}]'
    appended2 = reg.call(
        "transform.append",
        {"list_var": appended.value, "value": "b"},
    )
    assert appended2.value == '["a", {"id": 2}, "b"]'
    dict_result = reg.call(
        "transform.dict_set",
        {"dict_var": '{"a": 1}', "key": "b", "value": 2},
    )
    assert dict_result.value == '{"a": 1, "b": 2}'


def test_transform_get_path_nested_list_dict():
    reg = _transform()
    data = {"a": [{"b": [10, 20, 30]}]}
    assert reg.call("transform.get_path", {"data": data, "path": "a.0.b.1"}).value == 20
    assert reg.call("transform.get_path", {"data": data, "path": "a[0].b[-1]"}).value == 30
    missing = reg.call("transform.get_path", {"data": data, "path": "a.0.x"})
    assert not missing.ok
    default = reg.call(
        "transform.get_path",
        {"data": data, "path": "a.0.x", "required": False, "default": "fallback"},
    )
    assert default.value == "fallback"


def test_transform_index_key_split_join():
    reg = _transform()
    assert reg.call("transform.get_index", {"data": [1, 2, 3], "index": -1}).value == 3
    assert reg.call("transform.get_key", {"data": {"x": 9}, "key": "x"}).value == 9
    assert reg.call("transform.split", {"text": "a,b,c", "separator": ","}).value == [
        "a",
        "b",
        "c",
    ]
    assert (
        reg.call("transform.split", {"text": "a,b,c", "separator": ",", "maxsplit": 1}).value
        == ["a", "b,c"]
    )
    assert reg.call("transform.join", {"values": [1, 2, 3], "separator": "-"}).value == "1-2-3"


def test_transform_string_search_replace_compare():
    reg = _transform()
    assert reg.call("transform.contains", {"text": "Hello", "needle": "ell"}).value is True
    assert (
        reg.call(
            "transform.contains",
            {"text": "Hello", "needle": "ELL", "ignore_case": True},
        ).value
        is True
    )
    assert reg.call("transform.index_of", {"text": "abcabc", "needle": "bc"}).value == 1
    assert (
        reg.call("transform.replace", {"text": "a-b-c", "old": "-", "new": "_"}).value
        == "a_b_c"
    )
    assert (
        reg.call(
            "transform.compare",
            {"a": "ABC", "b": "abc", "op": "eq", "ignore_case": True},
        ).value
        is True
    )
    assert reg.call("transform.compare", {"a": 3, "b": 2, "op": "gt"}).value is True


def test_transform_conversion_json_regex():
    reg = _transform()
    assert reg.call("transform.to_int", {"value": "42"}).value == 42
    assert reg.call("transform.to_number", {"value": "4.5"}).value == 4.5
    assert reg.call("transform.to_bool", {"value": "yes"}).value is True
    assert reg.call("transform.to_string", {"value": {"a": 1}}).value == '{"a": 1}'
    parsed = reg.call("transform.json_parse", {"text": '{"a": [1, 2]}'})
    assert parsed.value == {"a": [1, 2]}
    assert reg.call("transform.json_dumps", {"value": {"a": 1}}).value == '{"a": 1}'
    assert (
        reg.call("transform.regex_match", {"text": "abc123", "pattern": r"[a-z]+\d+"}).value
        is True
    )
    assert (
        reg.call(
            "transform.regex_extract",
            {"text": "id=42", "pattern": r"id=(\d+)", "group": 1},
        ).value
        == "42"
    )
    assert reg.call(
        "transform.regex_findall", {"text": "a1 b2", "pattern": r"[a-z]\d"}
    ).value == ["a1", "b2"]


def test_compute_extended_arithmetic():
    reg = _compute()
    assert reg.call("compute.subtract", {"a": 5, "b": 2}).value == 3
    assert reg.call("compute.divide", {"a": 5, "b": 2}).value == 2.5
    assert not reg.call("compute.divide", {"a": 1, "b": 0}).ok
    assert reg.call("compute.floor_divide", {"a": 7, "b": 2}).value == 3
    assert reg.call("compute.modulo", {"a": 7, "b": 3}).value == 1
    assert reg.call("compute.power", {"a": 2, "b": 3}).value == 8
    assert reg.call("compute.sqrt", {"value": 9}).value == 3
    assert not reg.call("compute.sqrt", {"value": -1}).ok
    assert reg.call("compute.abs_value", {"value": -3}).value == 3
    assert reg.call("compute.negate", {"value": 3}).value == -3
    assert reg.call("compute.round_value", {"value": 2.346, "digits": 2}).value == 2.35
    assert reg.call("compute.min_values", {"values": [3, 1, 2]}).value == 1
    assert reg.call("compute.max_values", {"values": [3, 1, 2]}).value == 3
    assert reg.call("compute.average", {"values": [1, 2, 3]}).value == 2
    assert reg.call("compute.clamp", {"value": 9, "low": 0, "high": 5}).value == 5
    assert reg.call("compute.percentage", {"part": 25, "total": 200}).value == 12.5
    assert reg.call("compute.increment", {"value": 2, "step": 3}).value == 5
    assert reg.call("compute.decrement", {"value": 5, "step": 2}).value == 3
    assert reg.call("compute.compare", {"a": 2, "b": 2, "op": "ge"}).value is True
