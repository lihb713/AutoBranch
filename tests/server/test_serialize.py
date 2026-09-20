"""出参 JSON 安全序列化测试（Change A 任务 2.3）。

覆盖：标量原样、PageRef 折叠为 {page_id,url}、对象 str(value)、超长截断。
"""

from __future__ import annotations

from autobranch.schema.models import PageRef
from autobranch.server.services.runs import serialize_outputs


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


def test_long_string_truncated():
    out = serialize_outputs({"long": "x" * 5000})
    assert len(out["long"]) == 2001  # 截断到上限 + "…"
    assert out["long"].endswith("…")
    assert out["long"].startswith("x" * 2000)
