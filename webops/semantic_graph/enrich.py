"""结构富集（契约 §8.3 ②、§7.7）：role 归一化 + part-of + 表格框架 value-of 边。

- role 归一化（``webops.semantic_graph.models.normalize_role``）：把 M1 返回的
  role 收敛到契约 §7.5.3 枚举，供序列化前缀与下游判断。
- part-of 从属边在 ``programmatic.build_part_of_edges`` 生成（origin=structural，
  按视觉顺序）。
- value-of 边由表格框架派生：表头列（th/column）→ 该列单元格元素（§7.7 ③）。
"""

from __future__ import annotations

from webops.semantic_graph.models import Edge
from webops.semantic_graph.selection import SemanticTree


def derive_value_of_edges(tree: SemanticTree) -> list[Edge]:
    """从表格框架派生 value-of 边（§7.7 ③，origin=structural）。

    对每个 table 区域：首行（thead/首行）的 column 元素作为列头，其后各行
    按视觉列序把 cell 元素归属到对应列头，体现"该列单元格文本是该字段的值"。
    """
    edges: list[Edge] = []
    tables = [region for region in tree.regions if region.region_type == "table"]
    for table in tables:
        rows = _descendant_rows(tree, table.id)
        if not rows:
            continue
        header = _row_columns(tree, rows[0])
        if not header:
            continue
        for row in rows[1:]:
            cells = _row_cells(tree, row)
            for index, cell_id in enumerate(cells):
                if index >= len(header):
                    break
                edges.append(
                    Edge(
                        id="",
                        type="value-of",
                        from_id=cell_id,
                        to_id=header[index],
                        origin="structural",
                        reason="表格框架",
                        detail=f"第{index + 1}列: 列头={_label_of(tree, header[index])}",
                    )
                )
    return edges


def _descendant_rows(tree: SemanticTree, table_id: str) -> list[str]:
    """表格下的行区域（视觉顺序），含 rowgroup（thead/tbody）内嵌套的行。"""
    rows: list[str] = []
    for child_id in tree.children.get(table_id, []):
        region = _region(tree, child_id)
        if region is None:
            continue
        if region.region_type == "row":
            rows.append(region.id)
        elif region.region_type == "rowgroup":
            rows.extend(_descendant_rows(tree, region.id))
    return rows


def _row_columns(tree: SemanticTree, row_id: str) -> list[str]:
    """表头行的 column 元素（视觉列序）。"""
    return [
        element.id
        for child_id in tree.children.get(row_id, [])
        if (element := tree.element(child_id)) is not None and element.role == "column"
    ]


def _row_cells(tree: SemanticTree, row_id: str) -> list[str]:
    """数据行的 cell 元素（视觉列序）。"""
    return [
        element.id
        for child_id in tree.children.get(row_id, [])
        if (element := tree.element(child_id)) is not None and element.role == "cell"
    ]


def _region(tree: SemanticTree, region_id: str):
    for region in tree.regions:
        if region.id == region_id:
            return region
    return None


def _label_of(tree: SemanticTree, element_id: str) -> str:
    element = tree.element(element_id)
    if element is None:
        return ""
    return element.purpose or element.state.text or element.role
