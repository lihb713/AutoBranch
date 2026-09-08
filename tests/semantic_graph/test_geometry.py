"""M4 任务 2.3：几何计算（bounds、可见性、阅读顺序即兄弟按视觉顺序排序）。

fixture 断言 bounds 与兄弟排序（§8.3 ③、§7.6.1 原则 2）。
"""

from __future__ import annotations

from snapshot_factory import SnapshotBuilder, login_snapshot

from webops.browser.models import ElementNode
from webops.semantic_graph.geometry import sort_children, union_bounds, visual_key
from webops.semantic_graph.programmatic import build_part_of_edges, run_programmatic
from webops.semantic_graph.selection import build_semantic_tree


class TestVisualKey:
    """视觉排序键：先按行（y 上→下）、行内按列（x 左→右）。"""

    def test_order_by_row_then_column(self):
        b = SnapshotBuilder()
        a = b.node("button", x=10, y=50, w=10, h=10)  # 下行
        c = b.node("button", x=80, y=10, w=10, h=10)  # 上行右侧
        d = b.node("button", x=10, y=10, w=10, h=10)  # 上行左侧
        ordered = sorted([a, c, d], key=visual_key)
        assert [node.id for node in ordered] == [d.id, c.id, a.id]

    def test_missing_bounds_first(self):
        b = SnapshotBuilder()
        no_bounds = ElementNode(
            id="N0", tag="button", role="button", bounds=None, children=[]
        )
        with_bounds = b.node("button", x=10, y=10, w=5, h=5)
        # bounds=None 归零（(0,0) 最小），保持稳定排序
        assert visual_key(no_bounds) == (0.0, 0.0)
        assert visual_key(no_bounds) < visual_key(with_bounds)


class TestSiblingVisualOrder:
    """§7.6.1：兄弟节点按视觉顺序排列（从左到右、从上到下）。"""

    def test_login_form_siblings_in_reading_order(self):
        tree = build_semantic_tree(login_snapshot())
        sort_children(tree)
        by_id = {element.id: element for element in tree.elements}
        form_children = tree.children["F1"]
        ordered = [by_id[node_id].dom_node_id for node_id in form_children]
        assert ordered == [
            "n-user-label",
            "n-username",
            "n-pass-label",
            "n-password",
            "n-remember-label",
            "n-remember",
            "n-login",
            "n-forgot",
        ]

    def test_nav_siblings_left_to_right(self):
        tree = build_semantic_tree(login_snapshot())
        sort_children(tree)
        by_id = {element.id: element for element in tree.elements}
        nav_children = tree.children["N1"]
        assert [by_id[node_id].dom_node_id for node_id in nav_children] == [
            "n-orders",
            "n-report",
        ]

    def test_refs_follow_reading_order(self):
        result = run_programmatic(login_snapshot())
        order = [
            element.ref
            for element in sorted(result.tree.elements, key=lambda e: visual_key(e))
        ]
        expected = ["[1]", "[2]", "[3]", "[4]", "[5]", "[6]", "[7]", "[8]", "[9]", "[10]", "[11]"]
        assert order == expected


class TestBounds:
    """bounds 透传与区域外接矩形（§7.5.2/§7.5.3）。"""

    def test_element_bounds_preserved(self):
        result = run_programmatic(login_snapshot())
        username = next(e for e in result.tree.elements if e.dom_node_id == "n-username")
        assert username.bounds.x == 70
        assert username.bounds.y == 20
        assert username.bounds.w == 120
        assert username.bounds.h == 18

    def test_region_bounds(self):
        result = run_programmatic(login_snapshot())
        form = next(r for r in result.tree.regions if r.id == "F1")
        assert form.bounds.x == 10
        assert form.bounds.y == 10

    def test_union_bounds(self):
        b = SnapshotBuilder()
        a = b.node("span", x=10, y=20, w=10, h=10).bounds
        c = b.node("span", x=30, y=40, w=20, h=10).bounds
        merged = union_bounds([a, c])
        assert merged.x == 10
        assert merged.y == 20
        assert merged.w == 40
        assert merged.h == 30

    def test_union_bounds_empty(self):
        assert union_bounds([]) is None


class TestPartOfEdgeOrderIsVisual:
    """part-of 边序 = 兄弟视觉顺序（序列化缩进即视觉顺序，§7.6.1）。"""

    def test_edge_order_matches_sibling_order(self):
        tree = build_semantic_tree(login_snapshot())
        sort_children(tree)
        edges = build_part_of_edges(tree)
        form_edges = [edge for edge in edges if edge.to_id == "F1"]
        by_id = {element.id: element for element in tree.elements}
        ordered = [by_id[edge.from_id].dom_node_id for edge in form_edges]
        assert ordered == [
            "n-user-label",
            "n-username",
            "n-pass-label",
            "n-password",
            "n-remember-label",
            "n-remember",
            "n-login",
            "n-forgot",
        ]
