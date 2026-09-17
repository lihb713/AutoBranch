"""候选元素筛选与语义容器分类（契约 §8.4、§8.3 ①②）。

规则（§8.4）：
① 可交互 + 携带文本的元素必进（文本作为 ``state.text`` 属性，不单独成节点）；
② 语义容器（form/table/dialog/nav/section/fieldset/ul/tr...）进图作层级骨架与区域边界；
③ 纯定位 div/span 不占独立层级，只用于通过 DOM 祖先确定元素归属；
④ 语义容器嵌套深度由 LOD 控制（见 ``autobranch.semantic_graph.lod``）；
⑤ 隐藏/零尺寸/aria-hidden 由 M1 爬取时已剔除（§8.4 ⑤），本模块处理容器分类。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from autobranch.plugins.browser.driver.models import DomSnapshot, ElementNode
from autobranch.plugins.browser.semantic_graph.models import Element, Region, normalize_role
from autobranch.plugins.browser.semantic_graph.values import read_state

# 语义容器标签 → 区域类型（§8.4 ②；tr/tbody 等为表格框架骨架）
CONTAINER_TAGS: dict[str, str] = {
    "form": "form",
    "table": "table",
    "nav": "nav",
    "section": "section",
    "dialog": "dialog",
    "fieldset": "group",
    "ul": "list",
    "ol": "list",
    "dl": "list",
    "tr": "row",
    "tbody": "rowgroup",
    "thead": "rowgroup",
    "tfoot": "rowgroup",
    "aside": "section",
    "header": "section",
    "footer": "section",
    "main": "section",
}

INTERACTIVE_TAGS = frozenset({"input", "button", "a", "select", "textarea"})

# 区域类型 → ref 前缀（§7.5.2 示例 FORM F1 / TABLE T1 / NAV N1 / ROW R1）
REGION_PREFIX: dict[str, str] = {
    "form": "F",
    "table": "T",
    "row": "R",
    "rowgroup": "G",
    "list": "L",
    "nav": "N",
    "section": "S",
    "dialog": "D",
    "group": "GS",
}


@dataclass
class SemanticTree:
    """程序化阶段产物：语义容器层级树 + 候选元素 + 归属关系。

    :param children: 归属映射（父节点 id → 子节点 id 列表，DOM 顺序；
      几何阶段按视觉顺序重排，§7.6.1）。
    :param owner: 元素 id → 所属区域 id（part-of 便捷索引，§8.4 ③ 归属判定）。
    """

    regions: list[Region] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)
    children: dict[str, list[str]] = field(default_factory=dict)
    owner: dict[str, str] = field(default_factory=dict)

    def element(self, element_id: str) -> Element | None:
        """按 id 查元素。"""
        return next((element for element in self.elements if element.id == element_id), None)


def classify(node: ElementNode) -> str:
    """分类节点：``container`` / ``interactive`` / ``text`` / ``pure``（§8.4 ①②③）。"""
    tag = node.tag.lower()
    if tag in CONTAINER_TAGS:
        return "container"
    if tag in INTERACTIVE_TAGS:
        return "interactive"
    if node.text and node.text.strip():
        return "text"
    return "pure"


def build_semantic_tree(snapshot: DomSnapshot) -> SemanticTree:
    """从 DOM 快照构建语义树（候选筛选 + 语义容器骨架 + 归属，§8.3 ①②）。

    纯定位 div/span（``pure``）不生成节点，其子节点归属到最近语义容器
    （§8.4 ③ 只用于确定归属，不占独立层级）。
    """
    builder = _TreeBuilder()
    if snapshot.root is not None:
        builder.walk(snapshot.root, None)
    return builder.tree


class _TreeBuilder:
    """语义树构造器（维护区域/元素自增 id）。"""

    def __init__(self) -> None:
        self.tree = SemanticTree()
        self._region_counters: dict[str, int] = {}
        self._element_index = 0

    def walk(self, node: ElementNode, parent_region: Region | None) -> None:
        category = classify(node)
        if category == "container":
            region = self._make_region(node, parent_region)
            for child in node.children:
                self.walk(child, region)
        elif category in ("interactive", "text"):
            self._make_element(node, parent_region)
            for child in node.children:
                self.walk(child, parent_region)
        else:
            # 纯定位 div/span：子节点归属到最近语义容器（§8.4 ③）
            for child in node.children:
                self.walk(child, parent_region)

    def _make_region(self, node: ElementNode, parent_region: Region | None) -> Region:
        region_type = CONTAINER_TAGS.get(node.tag.lower(), "section")
        prefix = REGION_PREFIX.get(region_type, "R")
        number = self._region_counters.get(prefix, 0) + 1
        self._region_counters[prefix] = number
        region = Region(
            id=f"{prefix}{number}",
            ref=f"[{prefix}{number}]",
            region_type=region_type,
            bounds=node.bounds,
            depth=(parent_region.depth + 1) if parent_region else 0,
        )
        self.tree.regions.append(region)
        self._attach(region, parent_region)
        return region

    def _make_element(self, node: ElementNode, parent_region: Region | None) -> Element:
        self._element_index += 1
        element = Element(
            id=f"E{self._element_index}",
            ref="",
            role=normalize_role(node.role),
            state=read_state(node),
            options=list(node.options),
            bounds=node.bounds,
            dom_node_id=node.id,
            tag=node.tag,
        )
        self.tree.elements.append(element)
        self._attach(element, parent_region)
        return element

    def _attach(self, node: Element | Region, parent_region: Region | None) -> None:
        if parent_region is None:
            self.tree.children.setdefault("root", []).append(node.id)
            return
        parent_region.child_elements.append(node.id)
        self.tree.children.setdefault(parent_region.id, []).append(node.id)
        if isinstance(node, Element):
            self.tree.owner[node.id] = parent_region.id
