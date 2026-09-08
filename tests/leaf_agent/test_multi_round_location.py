"""任务 6.1：多轮定位（LLM 多次调用 semantic_graph 缩小/放大，搜索权归 LLM）。"""

from __future__ import annotations

from fake_transport import chat_response
from leaf_agent_helpers import graph_result, make_ctx, tool_call

from webops.browser import OpResult
from webops.leaf_agent import execute_leaf
from webops.parser.models import ActionNode


def test_multi_round_location_narrows_then_acts(config, fake, stub_engine):
    """6.1 LLM 逐步缩小范围（full→F1→F1/lod3）定位后点击，最终成功。"""
    fake.responses = [
        chat_response(tool_calls=[tool_call("semantic_graph", {"scope": "full", "lod": 2})]),
        chat_response(tool_calls=[tool_call("semantic_graph", {"scope": "F1", "lod": 2})]),
        chat_response(tool_calls=[tool_call("semantic_graph", {"scope": "F1", "lod": 3})]),
        chat_response(tool_calls=[tool_call("click", {"ref": "[3]"})]),
        chat_response(text="结果: 成功"),
    ]

    def _graph(name, arguments):
        scope = (arguments or {}).get("scope", "full")
        return graph_result(f"PAGE: 测试  URL=x\n区域 {scope} 详情")

    stub_engine.results["semantic_graph"] = _graph
    stub_engine.results["click"] = OpResult(True, detail={})

    result = execute_leaf(
        ActionNode(description="点击目标按钮"),
        make_ctx(config, fake, stub_engine),
    )

    assert result.status == "success"
    scopes = [call[1].get("scope") for call in stub_engine.calls if call[0] == "semantic_graph"]
    assert scopes == ["full", "full", "F1", "F1"]
    assert [c.name for c in result.trace.calls] == [
        "semantic_graph",
        "semantic_graph",
        "semantic_graph",
        "click",
    ]
    assert result.trace.calls[2].arguments == {"scope": "F1", "lod": 3}
