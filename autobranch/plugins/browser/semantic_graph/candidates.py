"""related-to 几何候选预筛（契约 §8.3 ③、§8.7、design D3）。

程序化阶段按 bounds 邻近性为每个元素产出 related-to 候选输入（不直接成边，
只作 LLM 打分的候选集，§8.5/§8.7）。语义打分与理由由 LLM 每次生成时填充。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from autobranch.plugins.browser.driver.models import Bounds
from autobranch.plugins.browser.semantic_graph.models import Element

# 每个目标元素最多保留的候选关联数（控制 LLM 输入规模）
MAX_PAIRS_PER_ELEMENT = 8


@dataclass
class RelatedPair:
    """related-to 几何候选（程序化预筛，待 LLM 打分）。

    :param detail: 推断依据（视觉邻近方位，如 "左侧邻近" / "上方邻近"）。
    :param distance: 中心欧氏距离（用于排序）。
    """

    from_id: str
    to_id: str
    detail: str = ""
    distance: float = math.inf


def geometric_candidates(
    elements: list[Element], max_per_element: int = MAX_PAIRS_PER_ELEMENT
) -> list[RelatedPair]:
    """按 bounds 邻近性产出 related-to 候选集（不直接成边）。

    对每个有包围盒的元素，按中心距离升序取最近 ``max_per_element`` 个其他元素；
    方位按水平/垂直带判定（同带内 → 左右；跨带 → 上下），写为推断依据。
    """
    pairs: list[RelatedPair] = []
    with_bounds = [element for element in elements if element.bounds is not None]
    for target in with_bounds:
        counted = 0
        for other in sorted(with_bounds, key=lambda item: _distance(target.bounds, item.bounds)):
            if other.id == target.id:
                continue
            pairs.append(
                RelatedPair(
                    from_id=other.id,
                    to_id=target.id,
                    detail=_proximity_desc(other.bounds, target.bounds),
                    distance=_distance(other.bounds, target.bounds),
                )
            )
            counted += 1
            if counted >= max_per_element:
                break
    return pairs


def _proximity_desc(source: Bounds, target: Bounds) -> str:
    """推断依据：source 相对 target 的方位（视觉邻近描述）。"""
    dy = _center(source)[1] - _center(target)[1]
    dx = _center(source)[0] - _center(target)[0]
    if abs(dy) > abs(dx):
        return "上方邻近" if dy < 0 else "下方邻近"
    return "左侧邻近" if dx < 0 else "右侧邻近"


def _distance(source: Bounds, target: Bounds) -> float:
    dx = _center(target)[0] - _center(source)[0]
    dy = _center(target)[1] - _center(source)[1]
    return math.hypot(dx, dy)


def _center(bounds: Bounds) -> tuple[float, float]:
    return (bounds.x + bounds.w / 2, bounds.y + bounds.h / 2)
