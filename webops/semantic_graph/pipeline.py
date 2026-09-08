"""语义图生成流水线（契约 §8.3/§8.5/§8.8/§9.5，design D4）。

两阶段流水线：程序化阶段（``run_programmatic``）+ LLM 填充阶段（``LlmFiller``），
每次调用都完整执行、无缓存。LOD 四维裁剪作用于统一生成结果之上：
深度/广度裁剪减少 LLM 输入规模（§9.5 ①②），属性/关联裁剪作用于最终输出（③④）。
"""

from __future__ import annotations

from webops.browser.models import DomSnapshot, LODSpec
from webops.semantic_graph.budget import check_budget
from webops.semantic_graph.errors import LlmStageError, ProgramStageError, SemanticGraphError
from webops.semantic_graph.llm_fill import LlmFiller
from webops.semantic_graph.lod import apply_attributes, crop_depth_breadth, filter_relations
from webops.semantic_graph.models import (
    Edge,
    PageInfo,
    Region,
    SemanticGraph,
    validate_graph,
)
from webops.semantic_graph.programmatic import run_programmatic
from webops.semantic_graph.refs import build_ref_map


def generate_semantic_graph(
    snapshot: DomSnapshot,
    scope: str = "full",
    lod: int | LODSpec = 3,
    filler: LlmFiller | None = None,
    budget_limit: int | None = None,
) -> SemanticGraph:
    """两阶段生成语义图（每次完整执行，无缓存，§8.8/§9.5）。

    :param scope: ``full`` 全页或指定区域 id（如 ``F1``/``T1``，§8.8 范围）。
    :param lod: LOD 级别 0~3 或 ``LODSpec``（§9.5 四维组合）。
    :param filler: ``LlmFiller`` 实现（LLM 填充阶段，§8.5 每次都要做）。
    :param budget_limit: token 预算上限（None 不检测，§8.8 ⑤）。
    """
    lod_spec = _coerce_lod(lod)
    programmatic = run_programmatic(snapshot)
    owner = programmatic.tree.owner
    regions, elements, structural_edges = (
        programmatic.tree.regions,
        programmatic.tree.elements,
        programmatic.edges,
    )
    candidates = programmatic.related_candidates

    # 范围参数：全页或指定区域 id（§8.8 范围控制广度维度）
    if scope != "full":
        regions, elements, structural_edges, candidates = _filter_scope(
            regions, elements, structural_edges, candidates, owner, scope
        )

    # LOD 深度/广度裁剪（§9.5 ①②）：减少 LLM 输入规模
    kept_regions, kept_elements = crop_depth_breadth(regions, elements, owner, lod_spec)
    kept_ids = {region.id for region in kept_regions} | {element.id for element in kept_elements}
    kept_edges = [
        edge
        for edge in structural_edges
        if edge.from_id in kept_ids and edge.to_id in kept_ids
    ]
    kept_candidates = [
        pair
        for pair in candidates
        if pair.from_id in kept_ids and pair.to_id in kept_ids
    ]

    # LLM 填充阶段（§8.5/§8.6/§8.7）：purpose + 区域 label + related-to 打分
    if filler is None:
        raise LlmStageError("LLM 填充器未注入（semantic_graph 每次都必须执行 LLM 填充阶段）")
    try:
        purpose_result = filler.fill_purpose(kept_elements, kept_regions)
        related_scores = filler.score_related_to(kept_candidates)
    except Exception as exc:  # LLM 填充失败（重试无意义，报告用户）
        raise LlmStageError(f"LLM 填充失败: {exc}") from exc

    _apply_purposes(kept_elements, purpose_result.element_purposes)
    _apply_region_labels(kept_regions, purpose_result.region_labels)
    related_edges = _build_related_edges(related_scores, kept_candidates, len(kept_edges))

    # LOD 属性/关联裁剪（§9.5 ③④）：作用于最终输出
    apply_attributes(kept_elements, lod_spec.attributes)
    final_edges = filter_relations(kept_edges + related_edges, lod_spec.relations)

    graph = SemanticGraph(
        page=PageInfo(url=snapshot.url, title=snapshot.title),
        regions=kept_regions,
        elements=kept_elements,
        edges=final_edges,
        ref_map=build_ref_map(kept_elements),
        viewport=snapshot.viewport or {},
    )
    problems = validate_graph(graph)
    if problems:
        raise SemanticGraphError("语义图校验失败: " + "; ".join(problems))
    if budget_limit is not None:
        check_budget(graph, budget_limit)
    return graph


def _coerce_lod(lod: int | LODSpec) -> LODSpec:
    if isinstance(lod, LODSpec):
        return lod
    return LODSpec.from_level(int(lod))


def _filter_scope(regions, elements, edges, candidates, owner, scope):
    """范围参数过滤（§8.8）：只保留指定区域及其子树。"""
    target = next(
        (region for region in regions if region.id == scope or region.ref.strip("[]") == scope),
        None,
    )
    if target is None:
        raise ProgramStageError(f"范围区域不存在: {scope}（应为区域 id 或 ref）")
    subtree = _collect_subtree(regions, edges, target.id)
    kept_regions = [region for region in regions if region.id in subtree]
    kept_elements = [element for element in elements if owner.get(element.id) in subtree]
    kept_ids = set(subtree) | {element.id for element in kept_elements}
    kept_edges = [edge for edge in edges if edge.from_id in kept_ids and edge.to_id in kept_ids]
    kept_candidates = [
        pair for pair in candidates if pair.from_id in kept_ids and pair.to_id in kept_ids
    ]
    return kept_regions, kept_elements, kept_edges, kept_candidates


def _collect_subtree(regions: list[Region], edges: list[Edge], root_id: str) -> set[str]:
    """收集区域子树（区域 id + 所有嵌套后代区域 id）。"""
    region_ids = {region.id for region in regions}
    parent: dict[str, str] = {}
    for edge in edges:
        if edge.type == "part-of" and edge.from_id in region_ids and edge.to_id in region_ids:
            parent[edge.from_id] = edge.to_id
    subtree = {root_id}
    changed = True
    while changed:
        changed = False
        for region_id in region_ids:
            if parent.get(region_id) in subtree and region_id not in subtree:
                subtree.add(region_id)
                changed = True
    return subtree


def _apply_purposes(elements, purposes: dict[str, str]) -> None:
    for element in elements:
        if element.id in purposes:
            element.purpose = purposes[element.id]


def _apply_region_labels(regions, labels: dict[str, str]) -> None:
    for region in regions:
        if region.id in labels:
            region.label = labels[region.id]
        elif not region.label:
            region.label = region.region_type


def _build_related_edges(related_scores, candidates, start_index: int) -> list[Edge]:
    """LLM 打分 → related-to 边（仅接受几何候选内的关联，§8.5 候选输入）。"""
    candidate_pairs = {(pair.from_id, pair.to_id): pair for pair in candidates}
    edges: list[Edge] = []
    for index, score in enumerate(related_scores, start=start_index + 1):
        pair = candidate_pairs.get((score.from_id, score.to_id))
        if pair is None:
            continue
        edges.append(
            Edge(
                id=f"ED{index}",
                type="related-to",
                from_id=score.from_id,
                to_id=score.to_id,
                origin="visual",
                confidence=score.confidence,
                score=score.score,
                reason=score.reason,
                detail=pair.detail,
            )
        )
    return edges
