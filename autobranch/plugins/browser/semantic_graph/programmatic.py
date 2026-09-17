"""程序化阶段编排（契约 §8.3 ①②③④、§8.4）：DOM 快照 → 语义骨架 + 几何候选。

纯程序、零 LLM，可独立测试。产出：区域骨架、候选元素（含程序化状态）、
part-of/value-of 结构边、related-to 几何候选输入（§8.5 待 LLM 打分）。
"""

from __future__ import annotations

from dataclasses import dataclass

from autobranch.plugins.browser.driver.models import DomSnapshot
from autobranch.plugins.browser.semantic_graph.candidates import RelatedPair, geometric_candidates
from autobranch.plugins.browser.semantic_graph.enrich import derive_value_of_edges
from autobranch.plugins.browser.semantic_graph.geometry import sort_children
from autobranch.plugins.browser.semantic_graph.models import Edge, RefMap
from autobranch.plugins.browser.semantic_graph.refs import assign_refs, build_ref_map
from autobranch.plugins.browser.semantic_graph.selection import SemanticTree, build_semantic_tree


@dataclass
class ProgrammaticResult:
    """程序化阶段产物（§8.3 ①②③④）。"""

    tree: SemanticTree
    edges: list[Edge]  # part-of + value-of（origin=structural，视觉顺序）
    related_candidates: list[RelatedPair]
    ref_map: RefMap


def run_programmatic(snapshot: DomSnapshot) -> ProgrammaticResult:
    """执行程序化阶段：候选筛选 + 结构富集 + 几何 + 程序化值 + 候选预筛。"""
    tree = build_semantic_tree(snapshot)
    sort_children(tree)
    edges = build_part_of_edges(tree)
    edges.extend(derive_value_of_edges(tree))
    edges = _renumber(edges)
    assign_refs(tree)
    return ProgrammaticResult(
        tree=tree,
        edges=edges,
        related_candidates=geometric_candidates(tree.elements),
        ref_map=build_ref_map(tree.elements),
    )


def build_part_of_edges(tree: SemanticTree) -> list[Edge]:
    """按视觉顺序生成 part-of 从属边（§8.3 ②，origin=structural）。

    顶层节点（直接挂文档）不产生 part-of 边；区域内元素与嵌套区域各一条。
    边顺序即子节点视觉顺序（树层级来自结构、兄弟顺序来自视觉，§7.6.1）。
    """
    edges: list[Edge] = []
    for parent_id, children in tree.children.items():
        if parent_id == "root":
            continue
        for child_id in children:
            if tree.element(child_id) is not None:
                reason, detail = "DOM 从属", "候选元素挂载在所属区域下"
            else:
                reason, detail = "语义容器嵌套", "嵌套区域层级"
            edges.append(
                Edge(
                    id="",
                    type="part-of",
                    from_id=child_id,
                    to_id=parent_id,
                    origin="structural",
                    reason=reason,
                    detail=detail,
                )
            )
    return edges


def _renumber(edges: list[Edge]) -> list[Edge]:
    for index, edge in enumerate(edges, start=1):
        edge.id = f"ED{index}"
    return edges
