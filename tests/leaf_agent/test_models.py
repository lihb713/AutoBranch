"""任务 1.1/1.2：ToolCallRecord 序列化与 LeafResult/LeafTrace 数据契约字段。"""

from __future__ import annotations

import json

from autobranch.leaf_agent.models import LeafResult, ToolCallRecord
from autobranch.reporting.models import LeafTrace
from autobranch.reporting.models import ToolCallRecord as M8Call


def test_tool_call_record_fields():
    """1.1 字段齐全：函数名/参数/工具结果/是否成功/时间戳。"""
    record = ToolCallRecord(
        name="click",
        arguments={"ref": "[1]"},
        result="失败: 元素不可点击",
        success=False,
        timestamp=123.0,
    )
    assert record.name == "click"
    assert record.arguments == {"ref": "[1]"}
    assert record.result == "失败: 元素不可点击"
    assert record.success is False
    assert record.timestamp == 123.0


def test_tool_call_record_serialize_round_trip():
    """1.1 序列化/反序列化往返一致（含 JSON 往返）。"""
    record = ToolCallRecord(
        name="type",
        arguments={"ref": "[2]", "text": "admin"},
        result="成功",
        success=True,
        timestamp=1.5,
    )
    assert ToolCallRecord.from_dict(record.to_dict()) == record
    data = json.loads(json.dumps(record.to_dict()))
    assert ToolCallRecord.from_dict(data) == record


def test_tool_call_record_serialize_handles_non_json_args():
    """1.1 参数中的非 JSON 值转为字符串，序列化不抛异常。"""
    record = ToolCallRecord(
        name="semantic_graph",
        arguments={"scope": "full", "lod": 2, "extra": object()},
        result="成功",
        success=True,
    )
    data = record.to_dict()
    assert isinstance(data["arguments"]["extra"], str)


def test_tool_call_record_to_m8_alignment():
    """1.1 → M8 对齐：去掉时间戳，字段与 M8 ``ToolCallRecord`` 一致。"""
    record = ToolCallRecord(
        name="click", arguments={"ref": "[1]"}, result="成功", success=True, timestamp=9.0
    )
    m8 = record.to_m8()
    assert isinstance(m8, M8Call)
    assert (m8.name, m8.arguments, m8.result, m8.success) == (
        "click",
        {"ref": "[1]"},
        "成功",
        True,
    )


def test_leaf_result_fields():
    """1.2 LeafResult 字段齐全：status/bool_value/error_source/trace。"""
    result = LeafResult(
        status="success",
        bool_value=True,
        error_source=None,
        trace=LeafTrace(llm_input={"node_type": "condition"}),
    )
    assert result.status == "success"
    assert result.bool_value is True
    assert result.error_source is None
    assert result.trace.llm_input == {"node_type": "condition"}


def test_leaf_trace_fields():
    """1.2 M8 ``LeafTrace`` 覆盖 M6 全部追踪字段（llm_input/reasoning/calls/terminator）。"""
    trace = LeafTrace(
        llm_input={"node_type": "action", "description": "点击登录"},
        llm_reasoning=["第1轮: 正在定位"],
        decision="结果: 成功",
        calls=[M8Call(name="click", success=True, result="成功")],
        terminator=None,
    )
    assert trace.llm_input["description"] == "点击登录"
    assert trace.llm_reasoning == ["第1轮: 正在定位"]
    assert trace.calls[0].name == "click"
    assert trace.terminator is None
