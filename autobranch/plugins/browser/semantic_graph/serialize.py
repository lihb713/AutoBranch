"""层次树序列化（契约 §7.6、spec 层次树序列化）。

引擎对象模型 → LLM 可读层次树文本：
- 区域 → ``REGION <type> <ref> <label>``
- 元素 → ``<缩进> <role前缀> [<ref>] <purpose> [状态]``，related-to 括号标注
- 文本承载元素 → ``<缩进> <role> [<ref>] <purpose>="<text>"``
- part-of 编码为缩进层级；兄弟按视觉顺序（几何阶段已排序，§7.6.1）
- value-of 并列在所属元素行内；id/bounds 不进文本，confidence 仅歧义时标注
- ref 由引擎确定性分配（refs.py），LLM 原样引用（§7.8）
"""

from __future__ import annotations

from autobranch.plugins.browser.semantic_graph.geometry import page_quadrant
from autobranch.plugins.browser.semantic_graph.models import (
    INTERACTIVE_ROLES,
    Edge,
    Element,
    Region,
    SemanticGraph,
)

# role → 行首前缀（契约 §7.6.2）
ROLE_PREFIX: dict[str, str] = {
    "textbox": "FIELD",
    "searchbox": "FIELD",
    "spinbutton": "FIELD",
    "slider": "FIELD",
    "combobox": "FIELD",
    "button": "ACTOR",
    "link": "LINK",
    "checkbox": "CHECK",
    "radio": "CHECK",
    "switch": "CHECK",
    "select": "SELECT",
    "row": "ROW",
    "cell": "CELL",
    "column": "CELL",
}

# 元素行里额外写出具体 role 的前缀（对齐 §7.6.4 示例 FIELD [1] textbox "..."）
ROLE_WORD_PREFIXES = frozenset(
    {"textbox", "searchbox", "spinbutton", "slider", "combobox", "button"}
)


def serialize(graph: SemanticGraph) -> str:
    """语义图 → LLM 层次树文本（§7.6，无尾部换行）。"""
    children = _children_index(graph)
    by_id = _node_index(graph)
    lines = [f"PAGE: {graph.page.title or '未命名'}  URL={graph.page.url}", ""]
    _render_children(children, "__root__", 0, graph, by_id, lines)
    return "\n".join(lines)


def _children_index(graph: SemanticGraph) -> dict[str, list[str]]:
    """由 part-of 边重建父子索引（边序 = 视觉顺序，§7.6.1）。"""
    children: dict[str, list[str]] = {}
    child_ids: set[str] = set()
    for edge in graph.edges:
        if edge.type == "part-of":
            children.setdefault(edge.to_id, []).append(edge.from_id)
            child_ids.add(edge.from_id)
    roots = [node.id for node in graph.elements if node.id not in child_ids]
    roots.extend(region.id for region in graph.regions if region.id not in child_ids)
    children["__root__"] = roots
    return children


def _node_index(graph: SemanticGraph) -> dict[str, Element | Region]:
    index: dict[str, Element | Region] = {}
    for element in graph.elements:
        index[element.id] = element
    for region in graph.regions:
        index[region.id] = region
    return index


def _render_children(
    children: dict[str, list[str]],
    parent_id: str,
    depth: int,
    graph: SemanticGraph,
    by_id: dict[str, Element | Region],
    lines: list[str],
) -> None:
    indent = "  " * depth
    viewport = graph.viewport
    for node_id in children.get(parent_id, []):
        node = by_id.get(node_id)
        if isinstance(node, Region):
            line = f"{indent}REGION {node.region_type.upper()} {node.ref.strip('[]')} {node.label}"
            quad = page_quadrant(node.bounds, viewport)
            if quad:
                line += f" (页面{quad})"
            lines.append(line)
            _render_children(children, node.id, depth + 1, graph, by_id, lines)
        elif isinstance(node, Element):
            lines.append(f"{indent}{render_element(node, graph.edges, by_id, viewport)}")


def render_element(
    element: Element,
    edges: list[Edge],
    by_id: dict[str, Element | Region],
    viewport: dict[str, int] | None = None,
) -> str:
    """渲染单个元素行（§7.6.2/§7.6.3）。"""
    if element.role in INTERACTIVE_ROLES:
        line = _interactive_line(element)
    else:
        line = _text_line(element)
    annotations = _related_annotations(element, edges, by_id)
    if annotations:
        line += "  " + " ".join(annotations)
    if element.confidence == "ambiguous":
        line += "  (歧义)"
    # 空间方位（§8.3 ③ 扩展）：稳定语义词，供 LLM 理解位置指令（如"右上角"）
    quad = page_quadrant(element.bounds, viewport)
    if quad:
        line += f"  (页面{quad})"
    return line
    return line


def _interactive_line(element: Element) -> str:
    prefix = ROLE_PREFIX.get(element.role, element.role)
    purpose = element.purpose or element.role
    parts = [f"{prefix} [{element.ref.strip('[]')}]"]
    if element.role in ROLE_WORD_PREFIXES:
        parts.append(element.role)
    parts.append(f'"{purpose}"')
    states = _render_states(element)
    if states:
        parts.append(states)
    # 可交互元素的文本（按钮/链接文字）是定位与判断的关键信息（§7.3 文本为
    # 元素属性；§7.6.2 text="..." 按钮/链接文本）。purpose 可能未含文本，故
    # 有文本时显式渲染，保证 LLM 一定可见。
    if element.state.text and element.state.text.strip():
        parts.append(f'text="{element.state.text.strip()}"')
    return " ".join(parts)


def _text_line(element: Element) -> str:
    prefix = ROLE_PREFIX.get(element.role, element.role)
    purpose = element.purpose or element.role
    return f'{prefix} [{element.ref.strip("[]")}] {purpose}="{element.state.text}"'


def _render_states(element: Element) -> str:
    """状态子集渲染（§7.6.2：value/checked/未选中/disabled/选项）。"""
    parts: list[str] = []
    state = element.state
    role = element.role
    if role in ("checkbox", "radio"):
        parts.append("checked" if state.checked else "未选中")
    if state.disabled:
        parts.append("disabled")
    if role == "select":
        parts.append(f'value="{state.selected}"')
        if element.options:
            parts.append("选项=" + "[" + ",".join(element.options) + "]")
    elif role in ("textbox", "searchbox", "spinbutton", "slider", "combobox"):
        parts.append(f'value="{state.value}"')
    elif role == "button" and element.tag == "input":
        # input[type=submit/button/reset] 按钮：标签在其 value 中（无子文本）
        parts.append(f'value="{state.value}"')
    return " ".join(parts)


def _related_annotations(
    element: Element, edges: list[Edge], by_id: dict[str, Element | Region]
) -> list[str]:
    """related-to 括号标注（§7.6.3：``(related-to: <来源> <分数>·<依据>)``）。"""
    annotations: list[str] = []
    for edge in edges:
        if edge.type != "related-to" or edge.to_id != element.id:
            continue
        source_label = _edge_source_label(edge, by_id)
        basis = edge.detail or edge.reason
        annotations.append(f'(related-to: "{source_label}" {edge.score}·{basis})')
    return annotations


def _edge_source_label(edge: Edge, by_id: dict[str, Element | Region]) -> str:
    """来源元素的 purpose（无则 role/id），§7.6.3 的来源元素标注。"""
    source = by_id.get(edge.from_id)
    if isinstance(source, Element):
        return source.purpose or source.role
    return edge.from_id
