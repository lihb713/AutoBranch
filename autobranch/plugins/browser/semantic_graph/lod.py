"""LOD 四维裁剪（契约 §9.5、design D4）。

先完整生成（程序化 + LLM 填充），再按 LODSpec 四维参数裁剪：
① 深度：语义容器嵌套层数；② 广度：纳入候选集合的元素数量；
③ 属性：每个节点携带字段多少；④ 关联：related-to 边详尽程度。

- LOD-0 深度=0/广度=direct/属性=minimal/关联=none
- LOD-1 深度=1/广度=region/属性=standard/关联=high
- LOD-2 深度=2/广度=region/属性=rich/关联=all
- LOD-3 深度=-1/广度=full/属性=full/关联=all
"""

from __future__ import annotations

from dataclasses import dataclass, field

from autobranch.plugins.browser.driver.models import LODSpec
from autobranch.plugins.browser.semantic_graph.candidates import RelatedPair
from autobranch.plugins.browser.semantic_graph.models import Edge, Element, Region

# 高分 related-to 阈值（LOD-1 关联=high，只列高分边，§9.5 ④）
HIGH_SCORE_THRESHOLD = 0.7


@dataclass
class CroppedParts:
    """裁剪后的图组成部分（§9.5 ①②③④ 作用于统一生成结果之上）。"""

    regions: list[Region] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    related_candidates: list[RelatedPair] = field(default_factory=list)


def crop_depth_breadth(
    regions: list[Region], elements: list[Element], owner: dict[str, str], lod: LODSpec
) -> tuple[list[Region], list[Element]]:
    """深度 + 广度裁剪（§9.5 ①②）：决定纳入候选集合的元素与区域。

    **深度（①）只裁剪语义容器（region）嵌套层数**：region.depth ≤ lod.depth
    （-1 不限）的容器骨架保留，深层容器骨架不展示（§8.4 语义容器作层级骨架，
    展示多少层由 LOD 深度决定）。

    **广度（②）决定元素的纳入范围**，不随 region 深度裁剪——可交互 + 携带
    文本的元素**必须进图**（§8.4 ①），不因所属容器嵌套深而被丢弃：
      - ``direct``：只含直接候选（容器层级 0 的元素 / 顶层元素）
      - ``region`` / ``full``：元素全部保留（含深层容器内元素）
    """
    max_depth = lod.depth if lod.depth >= 0 else float("inf")
    depth_map = {region.id: region.depth for region in regions}

    def element_level(element_id: str) -> int:
        region_id = owner.get(element_id)
        if region_id is None:
            return 0
        return depth_map.get(region_id, 0)

    kept_regions = [region for region in regions if region.depth <= max_depth]
    kept_region_ids = {region.id for region in kept_regions}

    # 元素裁剪只按广度（§8.4 可交互/文本必进），不随 region 深度丢弃。
    kept_elements: list[Element] = []
    for element in elements:
        level = element_level(element.id)
        if lod.breadth == "direct" and level > 0:
            continue
        kept_elements.append(element)

    kept_element_ids = {element.id for element in kept_elements}
    for region in kept_regions:
        region.child_elements = [
            child_id
            for child_id in region.child_elements
            if child_id in kept_element_ids or child_id in kept_region_ids
        ]
    return kept_regions, kept_elements


def prune_edges(edges: list[Edge], kept_ids: set[str]) -> list[Edge]:
    """剔除端点已被裁剪的边（边端点必须都在保留集合内）。"""
    return [edge for edge in edges if edge.from_id in kept_ids and edge.to_id in kept_ids]


def prune_candidates(candidates: list[RelatedPair], kept_ids: set[str]) -> list[RelatedPair]:
    """剔除端点已被裁剪的 related-to 候选。"""
    return [
        pair for pair in candidates if pair.from_id in kept_ids and pair.to_id in kept_ids
    ]


def apply_attributes(elements: list[Element], attributes: str) -> None:
    """属性维度裁剪（§9.5 ③）：每节点携带字段多少，原地修改元素对象。

    - ``minimal``：仅 role+名（purpose）；文本承载元素保留 text（其内容即信息）。
    - ``standard``：+ value/checked/disabled/selected（控件状态）。
    - ``rich``：+ options 与全量文本（相关文本）。
    - ``full``：全部字段。
    """
    for element in elements:
        state = element.state
        if attributes == "minimal":
            state.value = ""
            state.checked = None
            state.disabled = False
            state.selected = ""
            if not element.is_text_bearing:
                state.text = ""
            element.options = []
        elif attributes == "standard":
            if not element.is_text_bearing:
                state.text = ""
            element.options = []
        elif attributes == "rich":
            pass


def filter_relations(edges: list[Edge], relations: str) -> list[Edge]:
    """关联维度裁剪（§9.5 ④）：只作用于 related-to 边，part-of/value-of 始终保留。

    - ``none``：剔除全部 related-to。
    - ``high``：只保留高分边（score ≥ 0.7）。
    - ``all``：全部保留。
    """
    if relations == "all":
        return edges
    kept: list[Edge] = []
    for edge in edges:
        if edge.type != "related-to":
            kept.append(edge)
            continue
        if relations == "high" and edge.score >= HIGH_SCORE_THRESHOLD:
            kept.append(edge)
    return kept
