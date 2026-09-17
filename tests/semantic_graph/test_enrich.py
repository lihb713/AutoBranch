"""M4 任务 2.2：结构富集（role 归一化、part-of 从属边、表格框架 value-of 边）。

fixture 断言 part-of/value-of 边及 origin=structural（§8.3 ②、§7.7）。
"""

from __future__ import annotations

from autobranch.semantic_graph.enrich import derive_value_of_edges
from autobranch.semantic_graph.models import normalize_role
from autobranch.semantic_graph.selection import build_semantic_tree
from snapshot_factory import login_snapshot, orders_snapshot

from autobranch.semantic_graph import run_programmatic


class TestRoleNormalization:
    """§8.3 ②：role 归一化（M1 ARIA role → 契约枚举）。"""

    def test_listbox_to_select(self):
        assert normalize_role("listbox") == "select"

    def test_columnheader_to_column(self):
        assert normalize_role("columnheader") == "column"

    def test_unknown_role_passthrough(self):
        assert normalize_role("paragraph") == "paragraph"


class TestPartOfEdges:
    """§8.3 ②：part-of 从属边（DOM 树派生，origin=structural）。"""

    def test_element_part_of_region(self):
        result = run_programmatic(login_snapshot())
        part_of = [edge for edge in result.edges if edge.type == "part-of"]
        assert part_of, "应有 part-of 边"
        username = next(
            (e for e in result.tree.elements if e.dom_node_id == "n-username"), None
        )
        edge = next(e for e in part_of if e.from_id == username.id)
        assert edge.to_id == "F1"
        assert edge.origin == "structural"
        assert edge.type == "part-of"

    def test_region_nesting_edge(self):
        result = run_programmatic(orders_snapshot())
        part_of = [edge for edge in result.edges if edge.type == "part-of"]
        # 行区域挂载在 table/rowgroup 下
        row_ids = {r.id for r in result.tree.regions if r.region_type == "row"}
        nested = [edge for edge in part_of if edge.from_id in row_ids]
        assert nested
        assert all(edge.to_id.startswith(("T", "G")) for edge in nested)


class TestValueOfEdges:
    """§7.7 ③：表格框架派生的 value-of 边（origin=structural）。"""

    def test_cell_value_belongs_to_column(self):
        tree = build_semantic_tree(orders_snapshot())
        edges = derive_value_of_edges(tree)
        assert edges, "表格框架应派生 value-of 边"
        assert all(edge.type == "value-of" for edge in edges)
        assert all(edge.origin == "structural" for edge in edges)

    def test_amount_column_mapping(self):
        tree = build_semantic_tree(orders_snapshot())
        edges = derive_value_of_edges(tree)
        amount_header = next(
            e for e in tree.elements if e.dom_node_id == "n-h-amount"
        )
        amount_edges = [edge for edge in edges if edge.to_id == amount_header.id]
        # 金额列下两个单元格
        assert len(amount_edges) == 2
        texts = {
            tree.element(edge.from_id).state.text for edge in amount_edges
        }
        assert texts == {"¥98.00", "¥152.00"}
        assert all("第3列" in edge.detail for edge in amount_edges)

    def test_action_column_has_no_value_edge(self):
        tree = build_semantic_tree(orders_snapshot())
        edges = derive_value_of_edges(tree)
        action_header = next(
            e for e in tree.elements if e.dom_node_id == "n-h-action"
        )
        assert not any(edge.to_id == action_header.id for edge in edges)

    def test_no_value_edges_without_table(self):
        tree = build_semantic_tree(login_snapshot())
        assert derive_value_of_edges(tree) == []


class TestProgrammaticStructuralEdges:
    """程序化阶段输出的结构边（part-of + value-of，origin=structural）。"""

    def test_structural_edges_present(self):
        result = run_programmatic(orders_snapshot())
        structural = [edge for edge in result.edges if edge.origin == "structural"]
        assert any(edge.type == "part-of" for edge in structural)
        assert any(edge.type == "value-of" for edge in structural)
