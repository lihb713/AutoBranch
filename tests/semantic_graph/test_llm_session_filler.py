"""M4 任务 3.4：接入真实 M0 LLM 客户端（LLMSessionFiller 走 M0 传输层）。

通过 M0 的 ``FakeTransport``（tests/fake_transport.py）驱动 LLMSession 返回固定
JSON 响应，验证 purpose/related-to 解析写入正确。不改动 M0 测试文件。
"""

from __future__ import annotations

import json

import pytest
from fake_transport import FakeTransport, chat_response
from snapshot_factory import login_snapshot

from webops.llm.config import LLMConfig
from webops.llm.session import LLMSession
from webops.semantic_graph import LLMSessionFiller, generate_semantic_graph, run_programmatic
from webops.semantic_graph.errors import LlmStageError


def _session(responses: list) -> tuple[LLMSession, FakeTransport]:
    transport = FakeTransport(responses=responses)
    session = LLMSession(
        LLMConfig(base_url="https://api.test.example/v1", api_key="test-key", model="test-model"),
        system_prompt="你是 WebOps 页面语义分析器。",
        transport=transport,
    )
    return session, transport


class TestFillPurposeViaM0:
    """3.4：真实 M0 会话填充 purpose（ref 由引擎分配，模型原样引用）。"""

    def test_purpose_resolved_by_ref(self):
        programmatic = run_programmatic(login_snapshot())
        elements = programmatic.tree.elements[:4]
        purposes = {element.ref: element.state.text or element.role for element in elements}
        payload = {"purposes": purposes, "region_labels": {"F1": "登录区"}}
        session, transport = _session([chat_response(text=json.dumps(payload, ensure_ascii=False))])
        filler = LLMSessionFiller(session, programmatic.ref_map)
        result = filler.fill_purpose(elements, [programmatic.tree.regions[0]])
        assert transport.requests  # 确实发起了 M0 请求
        for element in elements:
            assert result.element_purposes[element.id] == purposes[element.ref]

    def test_region_label_resolved(self):
        programmatic = run_programmatic(login_snapshot())
        payload = {"purposes": {}, "region_labels": {"F1": "登录区"}}
        session, _ = _session([chat_response(text=json.dumps(payload, ensure_ascii=False))])
        filler = LLMSessionFiller(session, programmatic.ref_map)
        result = filler.fill_purpose([], programmatic.tree.regions[:1])
        assert result.region_labels["F1"] == "登录区"


class TestScoreRelatedViaM0:
    """3.4：真实 M0 会话填充 related-to 打分。"""

    def test_scores_resolved_by_ref(self):
        programmatic = run_programmatic(login_snapshot())
        username = next(e for e in programmatic.tree.elements if e.dom_node_id == "n-username")
        label = next(e for e in programmatic.tree.elements if e.dom_node_id == "n-user-label")
        payload = [
            {
                "from": label.ref,
                "to": username.ref,
                "score": 0.9,
                "reason": "这是用户名的标签",
                "confidence": "explicit",
            }
        ]
        session, _ = _session([chat_response(text=json.dumps(payload, ensure_ascii=False))])
        filler = LLMSessionFiller(session, programmatic.ref_map)
        scores = filler.score_related_to(programmatic.related_candidates)
        assert len(scores) == 1
        assert scores[0].from_id == label.id
        assert scores[0].to_id == username.id
        assert scores[0].score == 0.9
        assert scores[0].reason == "这是用户名的标签"

    def test_unresolvable_ref_skipped(self):
        programmatic = run_programmatic(login_snapshot())
        payload = [{"from": "[999]", "to": "[1]", "score": 0.5, "reason": "x"}]
        session, _ = _session([chat_response(text=json.dumps(payload))])
        filler = LLMSessionFiller(session, programmatic.ref_map)
        assert filler.score_related_to(programmatic.related_candidates) == []


class TestFullPipelineWithM0Filler:
    """3.4：semantic_graph 用真实 M0 填充器跑通（两阶段完整执行）。"""

    def test_pipeline_two_m0_requests(self):
        programmatic = run_programmatic(login_snapshot())
        purposes = {
            element.ref: element.state.text or element.role
            for element in programmatic.tree.elements
        }
        label = next(e for e in programmatic.tree.elements if e.dom_node_id == "n-user-label")
        username = next(e for e in programmatic.tree.elements if e.dom_node_id == "n-username")
        payload1 = {"purposes": purposes, "region_labels": {"F1": "登录区", "N1": "主导航"}}
        payload2 = [
            {
                "from": label.ref,
                "to": username.ref,
                "score": 0.9,
                "reason": "这是用户名的标签",
                "confidence": "explicit",
            }
        ]
        session, transport = _session(
            [
                chat_response(text=json.dumps(payload1, ensure_ascii=False)),
                chat_response(text=json.dumps(payload2, ensure_ascii=False)),
            ]
        )
        filler = LLMSessionFiller(session, programmatic.ref_map)
        graph = generate_semantic_graph(login_snapshot(), filler=filler)
        assert len(transport.requests) == 2  # purpose 请求 + related 请求
        assert all(element.purpose for element in graph.elements)
        related = [edge for edge in graph.edges if edge.type == "related-to"]
        assert related
        assert related[0].origin == "visual"
        assert related[0].score == 0.9


class TestParseFailure:
    """填充响应无法解析 → LlmStageError（§9.4，重试无意义）。"""

    def test_invalid_json_raises_llm_stage_error(self):
        programmatic = run_programmatic(login_snapshot())
        session, _ = _session([chat_response(text="这不是 JSON")])
        filler = LLMSessionFiller(session, programmatic.ref_map)
        with pytest.raises(LlmStageError):
            filler.fill_purpose(programmatic.tree.elements, [])

    def test_json_fence_tolerated(self):
        programmatic = run_programmatic(login_snapshot())
        payload = {"purposes": {}, "region_labels": {}}
        wrapped = f"```json\n{json.dumps(payload)}\n```"
        session, _ = _session([chat_response(text=wrapped)])
        filler = LLMSessionFiller(session, programmatic.ref_map)
        result = filler.fill_purpose([], [])
        assert result.element_purposes == {}
