"""M4 空间方位计算测试（§8.3 ③ 扩展：稳定方位词，供 LLM 理解位置指令）。

九宫格方位：top/middle/bottom × left/center/right，基于元素中心相对视口。
"""

from __future__ import annotations

from autobranch.browser.models import Bounds
from autobranch.semantic_graph.geometry import page_quadrant, quadrant_center

VIEWPORT = {"width": 900, "height": 600}


def test_top_right():
    # 视口 900x600：右上角区域（中心 x>600, y<200）
    assert page_quadrant(Bounds(x=700, y=20, w=80, h=30), VIEWPORT) == "top-right"


def test_bottom_left():
    assert page_quadrant(Bounds(x=30, y=500, w=60, h=40), VIEWPORT) == "bottom-left"


def test_top_center():
    # 中心 x 在 300~600 → center；y<200 → top
    assert page_quadrant(Bounds(x=350, y=50, w=100, h=30), VIEWPORT) == "top"


def test_middle_left():
    assert page_quadrant(Bounds(x=20, y=280, w=60, h=40), VIEWPORT) == "left"


def test_center():
    assert page_quadrant(Bounds(x=400, y=280, w=100, h=40), VIEWPORT) == "center"


def test_bottom_center():
    assert page_quadrant(Bounds(x=420, y=500, w=60, h=40), VIEWPORT) == "bottom"


def test_none_without_bounds():
    assert page_quadrant(None, VIEWPORT) is None


def test_none_without_viewport():
    assert page_quadrant(Bounds(x=10, y=10, w=10, h=10), None) is None
    assert page_quadrant(Bounds(x=10, y=10, w=10, h=10), {}) is None


def test_quadrant_center():
    cx, cy = quadrant_center(Bounds(x=100, y=50, w=20, h=10))
    assert (cx, cy) == (110.0, 55.0)
    assert quadrant_center(None) is None
