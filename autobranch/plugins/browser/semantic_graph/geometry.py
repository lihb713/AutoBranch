"""几何计算（契约 §8.3 ③、§7.6.1）：bounds、可见性、阅读顺序、空间方位。

- bounds 取自 M1 快照（视口坐标，§7.5.3），本模块计算区域包围盒与邻近性。
- 阅读顺序：兄弟节点按视觉顺序排列（从左到右、从上到下），实现为先按行
  （上→下）再按列（左→右）排序（§7.6.1 原则 2）。
- 空间方位（§8.3 ③ 扩展）：把元素中心相对视口位置映射为稳定语义词
  （九宫格：top/middle/bottom × left/center/right），供 LLM 理解
  「右上角 / 底部」等位置指令。方位是相对语义，不随页面滚动/布局小幅变化
  而失效（与绝对像素坐标不同）。
"""

from __future__ import annotations

from autobranch.plugins.browser.driver.models import Bounds
from autobranch.plugins.browser.semantic_graph.models import Element, Region
from autobranch.plugins.browser.semantic_graph.selection import SemanticTree


def visual_key(item: Element | Region) -> tuple[float, float]:
    """视觉排序键：先按行（y 上→下）、行内按列（x 左→右）。"""
    bounds = item.bounds
    if bounds is None:
        return (0.0, 0.0)
    return (bounds.y, bounds.x)


def sort_children(tree: SemanticTree) -> None:
    """按视觉顺序重排各父节点下的子节点（兄弟节点阅读顺序，§7.6.1）。"""
    for parent_id, children in tree.children.items():
        ordered = sorted(
            ((child_id, _find(tree, child_id)) for child_id in children),
            key=lambda pair: visual_key(pair[1]) if pair[1] is not None else (0.0, 0.0),
        )
        tree.children[parent_id] = [child_id for child_id, _ in ordered]


def _find(tree: SemanticTree, node_id: str) -> Element | Region | None:
    for region in tree.regions:
        if region.id == node_id:
            return region
    return tree.element(node_id)


def union_bounds(bounds_list: list[Bounds | None]) -> Bounds | None:
    """合并多个包围盒为最小外接矩形（区域包围盒兜底，§7.5.2）。"""
    present = [bounds for bounds in bounds_list if bounds is not None]
    if not present:
        return None
    return Bounds(
        x=min(bounds.x for bounds in present),
        y=min(bounds.y for bounds in present),
        w=max(bounds.x + bounds.w for bounds in present) - min(bounds.x for bounds in present),
        h=max(bounds.y + bounds.h for bounds in present) - min(bounds.y for bounds in present),
    )


# ---------------------------------------------------------------------------
# 空间方位（空间语义，§8.3 ③ 扩展）
# ---------------------------------------------------------------------------

#: 方位词（稳定语义，供 LLM 理解位置指令）
_HORIZONTAL = ("left", "center", "right")
_VERTICAL = ("top", "middle", "bottom")


def page_quadrant(bounds: Bounds | None, viewport: dict[str, int] | None) -> str | None:
    """元素相对页面的九宫格方位（如 ``top-right`` / ``bottom``）。

    基于元素中心点相对视口的位置计算；视口缺失时回落 None（无法判定方位）。
    方位是相对语义，页面小幅滚动/布局变化不影响词面（仅当元素跨视口边界
    时才可能改变），供 LLM 理解「右上角 / 页面底部」等位置指令。
    """
    if bounds is None:
        return None
    vw = viewport and viewport.get("width")
    vh = viewport and viewport.get("height")
    if not vw or not vh:
        return None
    cx = bounds.x + bounds.w / 2
    cy = bounds.y + bounds.h / 2
    h = _HORIZONTAL[0] if cx < vw / 3 else (_HORIZONTAL[2] if cx > vw * 2 / 3 else _HORIZONTAL[1])
    v = _VERTICAL[0] if cy < vh / 3 else (_VERTICAL[2] if cy > vh * 2 / 3 else _VERTICAL[1])
    if h == "center" and v == "middle":
        return "center"
    if h == "center":
        return v
    if v == "middle":
        return h
    return f"{v}-{h}"


def quadrant_center(bounds: Bounds | None) -> tuple[float, float] | None:
    """元素包围盒中心点（视口坐标，供坐标点击兜底，M5 使用）。"""
    if bounds is None:
        return None
    return (bounds.x + bounds.w / 2, bounds.y + bounds.h / 2)
