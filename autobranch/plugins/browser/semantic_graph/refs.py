"""ref 映射表（契约 §7.8 策略 B、spec 5.2）。

引擎确定性分配 ref：``[N]`` ↔ 元素 id ↔ DOM 节点 id 双向解析，LLM 只原样引用，
解析归引擎。会话内即用即弃（策略 B），不做跨快照身份跟踪。
"""

from __future__ import annotations

from autobranch.plugins.browser.semantic_graph.models import Element, RefMap
from autobranch.plugins.browser.semantic_graph.selection import SemanticTree


def assign_refs(tree: SemanticTree) -> None:
    """按阅读顺序为元素分配 ``[1]``、``[2]``...（§7.8，ref 锚点确定性）。"""
    for index, element_id in enumerate(_reading_order(tree), start=1):
        element = tree.element(element_id)
        element.ref = f"[{index}]"


def _reading_order(tree: SemanticTree) -> list[str]:
    """深度优先、兄弟按视觉顺序遍历区域/元素，返回元素 id 阅读顺序（§7.6.1）。"""
    result: list[str] = []

    def visit(parent_id: str) -> None:
        for child_id in tree.children.get(parent_id, []):
            if tree.element(child_id) is not None:
                result.append(child_id)
            else:
                visit(child_id)

    visit("root")
    return result


def build_ref_map(elements: list[Element]) -> RefMap:
    """从元素列表构造双向 ref 映射表（``[N]`` ↔ 元素 id ↔ DOM 节点 id）。"""
    ref_map = RefMap()
    for element in elements:
        ref_map.ref_to_element[element.ref] = element.id
        ref_map.element_to_ref[element.id] = element.ref
        ref_map.element_to_dom[element.id] = element.dom_node_id
    return ref_map
