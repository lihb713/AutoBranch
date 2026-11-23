"""出参 JSON 安全序列化测试（Change A 任务 2.3）。

覆盖：出参完整保留、PageRef 折叠、嵌套结构；黑板变量截断。
"""

from __future__ import annotations

from autobranch.schema.models import PageRef
from autobranch.server.services.runs import _json_safe_variable, serialize_outputs


class _FakeObj:
    def __str__(self) -> str:
        return "会话对象"


def test_scalars_passthrough():
    out = serialize_outputs({"s": "文本", "i": 42, "f": 1.5, "b": True, "n": None})
    assert out == {"s": "文本", "i": 42, "f": 1.5, "b": True, "n": None}


def test_page_ref_folded():
    out = serialize_outputs({"页": PageRef(page_id="p1", url="https://x")})
    assert out == {"页": {"page_id": "p1", "url": "https://x"}}


def test_object_str():
    out = serialize_outputs({"obj": _FakeObj()})
    assert out == {"obj": "会话对象"}


def test_long_output_string_not_truncated():
    out = serialize_outputs({"long": "x" * 5000})
    assert out["long"] == "x" * 5000
    assert not out["long"].endswith("…")


def test_nested_output_structure_and_page_ref_preserved():
    out = serialize_outputs(
        {"items": [{"page": PageRef(page_id="p1", url="https://x")}, 2]}
    )
    assert out == {
        "items": [{"page": {"page_id": "p1", "url": "https://x"}}, 2]
    }


def test_variable_metadata_marks_long_string():
    value, truncated, full_length = _json_safe_variable("x" * 5000)
    assert isinstance(value, str) and value.endswith("…")
    assert truncated is True
    assert full_length == 5000


def test_variable_metadata_scalar_not_truncated():
    assert _json_safe_variable(42) == (42, False, None)
