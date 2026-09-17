"""LLM 填充阶段（契约 §8.5/§8.6/§8.7、design D1）。

LLM 填充器（``LlmFiller``）为可注入依赖：``fill_purpose`` 填充每个候选元素
的 purpose（含区域 label），``score_related_to`` 基于几何候选产出 related-to
打分与理由。测试注入 mock（固定返回），真实实现走 M0 ``LLMSession``。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from autobranch.llm.session import LLMSession
from autobranch.plugins.browser.semantic_graph.errors import LlmStageError
from autobranch.plugins.browser.semantic_graph.models import Element, RefMap, Region


@dataclass
class PurposeResult:
    """purpose 填充结果（§8.6）：元素 purpose + 区域 label。"""

    element_purposes: dict[str, str] = field(default_factory=dict)
    region_labels: dict[str, str] = field(default_factory=dict)


@dataclass
class RelatedScore:
    """related-to 打分结果（§8.7）：一条关联边打分。"""

    from_id: str
    to_id: str
    score: float
    reason: str = ""
    confidence: str = "inferred"


class LlmFiller(Protocol):
    """可注入的 LLM 填充器接口（design D1，两阶段解耦边界）。"""

    def fill_purpose(self, elements: list[Element], regions: list[Region]) -> PurposeResult:
        """为候选元素填充 purpose、为区域填充 label（§8.6）。"""
        ...

    def score_related_to(self, candidates: list) -> list[RelatedScore]:
        """基于几何候选产出 related-to 打分与理由（§8.7）。"""
        ...


class MockFiller:
    """测试用 mock 填充器：固定返回预设 purpose 与打分（§8.5 mock 测试）。

    purpose 与 related 的 from/to 可按元素 id 或 DOM 快照节点 id（``dom_node_id``）
    键控，测试无需预知引擎分配的 E1/E2... id。
    """

    def __init__(
        self,
        purposes: dict[str, str] | None = None,
        region_labels: dict[str, str] | None = None,
        related: list[dict] | None = None,
    ) -> None:
        self._purposes = purposes or {}
        self._region_labels = region_labels or {}
        self._related = related or []
        self._lookup: dict[str, str] = {}

    def fill_purpose(self, elements: list[Element], regions: list[Region]) -> PurposeResult:
        self._lookup = {
            element.id: element.id for element in elements
        } | {element.dom_node_id: element.id for element in elements if element.dom_node_id}
        return PurposeResult(
            element_purposes={element.id: self._purpose_for(element) for element in elements},
            region_labels={
                region.id: self._region_labels.get(region.id, region.region_type)
                for region in regions
            },
        )

    def score_related_to(self, candidates: list) -> list[RelatedScore]:
        return [
            RelatedScore(
                from_id=self._lookup.get(item["from_id"], item["from_id"]),
                to_id=self._lookup.get(item["to_id"], item["to_id"]),
                score=float(item.get("score", 0.5)),
                reason=str(item.get("reason", "")),
                confidence=str(item.get("confidence", "inferred")),
            )
            for item in self._related
        ]

    def _purpose_for(self, element: Element) -> str:
        for key in (element.id, element.dom_node_id):
            if key in self._purposes:
                return self._purposes[key]
        return element.role


class LLMSessionFiller:
    """基于 M0 ``LLMSession`` 的真实填充器（spec §8.6/§8.7、任务 3.4）。

    每次填充发送一次请求，要求模型以 JSON 返回 purpose 映射 / related 打分。
    ref 由引擎分配并写入请求文本，模型只原样引用（§7.8，解析归引擎）。
    """

    def __init__(self, session: LLMSession, ref_map: RefMap) -> None:
        self._session = session
        self._ref_map = ref_map

    def fill_purpose(self, elements: list[Element], regions: list[Region]) -> PurposeResult:
        self._session.add_user_message(self._purpose_prompt(elements, regions))
        response = self._session.request()
        payload = _parse_json(response.text)
        purposes = payload.get("purposes") or {}
        labels = payload.get("region_labels") or {}
        return PurposeResult(
            element_purposes={
                element.id: purposes.get(element.ref, element.role) for element in elements
            },
            region_labels={
                region.id: labels.get(region.ref.strip("[]"), region.region_type)
                for region in regions
            },
        )

    def score_related_to(self, candidates: list) -> list[RelatedScore]:
        self._session.add_user_message(self._related_prompt(candidates))
        response = self._session.request()
        payload = _parse_json(response.text)
        items = payload if isinstance(payload, list) else payload.get("related") or []
        scores: list[RelatedScore] = []
        for item in items:
            from_id = self._resolve_ref(str(item.get("from", "")))
            to_id = self._resolve_ref(str(item.get("to", "")))
            if from_id is None or to_id is None:
                continue
            scores.append(
                RelatedScore(
                    from_id=from_id,
                    to_id=to_id,
                    score=float(item.get("score", 0.5)),
                    reason=str(item.get("reason", "")),
                    confidence=str(item.get("confidence", "inferred")),
                )
            )
        return scores

    def _resolve_ref(self, token: str) -> str | None:
        """``[N]`` → 元素 id（引擎解析，不信任 LLM 猜测，§7.8）。"""
        if token in self._ref_map.ref_to_element:
            return self._ref_map.ref_to_element[token]
        return None

    def _purpose_prompt(self, elements: list[Element], regions: list[Region]) -> str:
        lines = [
            "为以下页面元素填充作用（purpose），为区域填充 label（一句话说明区域）。",
            '只返回 JSON：{"purposes": {"[1]": "用户名输入框", ...},'
            ' "region_labels": {"F1": "登录区"}}',
        ]
        for region in regions:
            lines.append(f"REGION {region.region_type} {region.ref} 深度={region.depth}")
        for element in elements:
            text = element.state.text
            value = element.state.value
            lines.append(
                f"  {element.ref} role={element.role} text={text!r} value={value!r}"
            )
        return "\n".join(lines)

    def _related_prompt(self, candidates: list) -> str:
        lines = [
            "为以下元素关联候选打分（0~1；0.9=强关联，如'标签-控件'对），并给出理由。",
            '只返回 JSON 数组：[{"from": "[1]", "to": "[3]", "score": 0.9,'
            ' "reason": "这是用户名的标签", "confidence": "explicit"}]',
        ]
        for pair in candidates:
            source = self._ref_map.element_to_ref.get(pair.from_id, pair.from_id)
            target = self._ref_map.element_to_ref.get(pair.to_id, pair.to_id)
            lines.append(f"  {source} → {target}（{pair.detail}）")
        return "\n".join(lines)


def _parse_json(text: str):
    """解析 LLM 返回的 JSON（容忍 ```json 围栏）。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LlmStageError(f"LLM 填充响应无法解析: {exc}") from exc
