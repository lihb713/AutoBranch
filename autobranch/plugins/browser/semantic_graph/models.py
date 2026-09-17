"""语义图对象模型（契约 §7.5）。

- ``PageInfo`` / ``Region`` / ``Element`` / ``Edge`` / ``Change`` / ``SemanticGraph``：
  语义图数据契约（§7.5.1~§7.5.6）。元素统一为单一节点类型，文本记录在
  ``Element.state.text``（§7.3），三种边（part-of / value-of / related-to）。
- ``RefMap``：引擎确定性 ref 映射表（§7.8 策略 B，会话内即用即弃）——
  ``[N]`` ↔ 元素 id ↔ DOM 节点 id 双向解析，不依赖 LLM 猜测。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from autobranch.plugins.browser.driver.models import Bounds

# 可交互角色集合（§7.5.3/§7.6.2）：序列化渲染为元素行；非交互角色带文本时
# 作为文本承载元素渲染为 ``purpose="text"`` 形式（§7.5.4）。
INTERACTIVE_ROLES = frozenset(
    {
        "textbox",
        "searchbox",
        "spinbutton",
        "slider",
        "combobox",
        "button",
        "link",
        "checkbox",
        "radio",
        "switch",
        "select",
    }
)

# role 归一化映射（§8.3 ②，收敛到 §7.5.3 枚举）
ROLE_NORMALIZE: dict[str, str] = {
    "listbox": "select",
    "columnheader": "column",
}


def normalize_role(role: str) -> str:
    """role 归一化（§8.3 ②）：M1 返回的 ARIA role 收敛到契约枚举。"""
    return ROLE_NORMALIZE.get(role, role)


@dataclass
class PageInfo:
    """图根携带的页面信息（契约 §7.5.1）。"""

    url: str = ""
    title: str = ""
    page_type: str = "document"


@dataclass
class ElementState:
    """元素当前状态（程序化实时读取，契约 §7.5.3）。

    文本是元素属性（``state.text``），不单独成节点（§7.3）。
    """

    value: str = ""
    checked: bool | None = None
    disabled: bool = False
    visible: bool = True
    text: str = ""
    selected: str = ""


@dataclass
class Element:
    """元素节点（可交互 / 语义容器 / 纯文本承载共用，契约 §7.5.3/§7.5.4）。

    :param purpose: 元素作用，由 LLM 每次生成时填充（§8.6）。
    :param confidence: explicit / inferred / ambiguous（仅歧义时序列化标注）。
    :param dom_node_id: 对应 DOM 快照节点 id，供 ref 映射到 DOM 节点（§7.8）。
    """

    id: str
    ref: str
    role: str
    purpose: str = ""
    state: ElementState = field(default_factory=ElementState)
    options: list[str] = field(default_factory=list)
    bounds: Bounds | None = None
    confidence: str = "explicit"
    dom_node_id: str = ""
    tag: str = ""

    @property
    def is_text_bearing(self) -> bool:
        """是否为携带文本的元素（§7.5.4）。

        有非空文本即视为文本承载——**包括可交互元素**（button/a 等的按钮文字、
        链接文字同样承载定位/判断的关键信息，§8.4 ① 携带文本的元素必进）。
        仅 ``state.text`` 为空（如无文本的 input）时才非文本承载。
        """
        return bool(self.state.text.strip())


@dataclass
class Region:
    """区域节点（语义容器，层级骨架，契约 §7.5.2）。

    :param id: 区域 id（如 ``F1`` / ``T1``），与 ref 去括号一致。
    :param ref: LLM 可见引用（如 ``[F1]``）。
    :param depth: 语义容器嵌套层数（LOD 深度维度，§9.5 ①）。
    :param label: 区域语义，由 LLM 每次生成时填充；未填充时用 region_type。
    """

    id: str
    ref: str
    region_type: str
    label: str = ""
    scope: str = ""
    bounds: Bounds | None = None
    child_elements: list[str] = field(default_factory=list)
    depth: int = 0


@dataclass
class Edge:
    """关联边（契约 §7.5.5）。

    :param type: related-to / part-of / value-of。
    :param origin: visual（视觉几何）/ structural（DOM 结构）。
    :param score: 关联强度（0.0~1.0，相对排序无绝对阈值）。
    :param reason: 为何相关（LLM 理由 / 规则依据）。
    """

    id: str
    type: str
    from_id: str
    to_id: str
    origin: str = "structural"
    confidence: str = "explicit"
    score: float = 1.0
    reason: str = ""
    detail: str = ""


@dataclass
class Change:
    """变化段（可选，契约 §7.5.6）。本模块不做跨快照对比，默认空。"""

    type: str
    node_id: str
    summary: str = ""


@dataclass
class RefMap:
    """引擎确定性 ref 映射表（契约 §7.8 策略 B）。

    ``[N]`` ↔ 元素 id ↔ DOM 节点 id 双向解析。ref 由引擎分配，LLM 只原样引用。
    """

    ref_to_element: dict[str, str] = field(default_factory=dict)
    element_to_ref: dict[str, str] = field(default_factory=dict)
    element_to_dom: dict[str, str] = field(default_factory=dict)

    def resolve(self, ref: str) -> str | None:
        """``[N]`` → 元素 id；无此 ref 返回 None。"""
        return self.ref_to_element.get(ref)

    def dom_node_id(self, ref: str) -> str | None:
        """``[N]`` → DOM 快照节点 id；无此 ref 返回 None。"""
        element_id = self.resolve(ref)
        if element_id is None:
            return None
        return self.element_to_dom.get(element_id)


@dataclass
class SemanticGraph:
    """语义图（契约 §7.5.1）。

    :param ref_map: 引擎侧确定性 ref 映射表（§7.8），供机器侧校验/ref 解析/断言求值。
    """

    type: str = "semantic-graph"
    version: str = "0.1"
    page: PageInfo = field(default_factory=PageInfo)
    regions: list[Region] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    ref_map: RefMap = field(default_factory=RefMap)
    viewport: dict[str, int] = field(default_factory=dict)


def validate_graph(graph: SemanticGraph) -> list[str]:
    """校验语义图结构约束（元素 id/ref 唯一、边端点存在、ref 映射一致）。

    返回违规描述列表；空列表表示合法。
    """
    problems: list[str] = []
    element_ids = [element.id for element in graph.elements]
    refs = [element.ref for element in graph.elements]
    if len(set(element_ids)) != len(element_ids):
        problems.append("元素 id 不唯一")
    if len(set(refs)) != len(refs):
        problems.append("元素 ref 不唯一")
    region_ids = [region.id for region in graph.regions]
    if len(set(region_ids)) != len(region_ids):
        problems.append("区域 id 不唯一")
    known = set(element_ids) | set(region_ids)
    for edge in graph.edges:
        if edge.from_id not in known:
            problems.append(f"边 {edge.id} from 端点不存在: {edge.from_id}")
        if edge.to_id not in known:
            problems.append(f"边 {edge.id} to 端点不存在: {edge.to_id}")
    for element in graph.elements:
        if element.ref not in graph.ref_map.ref_to_element:
            problems.append(f"元素 {element.id} 的 ref {element.ref} 不在 ref 映射表中")
    return problems
