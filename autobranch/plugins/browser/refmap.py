"""引擎侧 ref 确定性解析（契约 §7.8 策略 B、M5 spec §5.3）。

``EngineRefMap`` 维护 ref ↔ 引擎侧元素 id ↔ DOM 快照节点的确定性映射，
并把 DOM 节点转换为 M1 可定位的 CSS 选择器（``ElementRef.id`` 语义，
契约 §5.8.1：M1 层把 id 解释为 CSS 选择器）。

- **即用即弃**（策略 B）：每次 ``semantic_graph`` 完整生成即刷新映射表、
  作废旧 ref；旧 ref 调用返回「过期」拒绝（请重新获取快照）。
- **URL 导航失效**：页面 URL 与生成快照时的 URL 不一致时，ref 视为过期。
- **确定性**：ref 由引擎分配，LLM 只原样引用；解析归引擎，不信任 LLM。

选择器推导：节点有 ``dom_id``（DOM ``id`` 属性）时用 ``#<dom_id>``；否则
基于快照树重建的祖先标签路径（``body > form > input``，尽力确定性定位，
中间被过滤的节点会导致路径不精确，交由 M1 操作失败回传——可恢复错误）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from autobranch.plugins.browser.driver import DomSnapshot, ElementNode
from autobranch.plugins.browser.semantic_graph import Element, SemanticGraph

_RESOLVE_VALID = "valid"
_RESOLVE_STALE = "stale"
_RESOLVE_INVALID = "invalid"


@dataclass(frozen=True)
class RefResolution:
    """一次 ref 解析结果：引擎侧元素 id + 定位选择器 + 快照状态。"""

    ref: str
    element_id: str
    dom_node_id: str
    selector: str
    tag: str
    role: str
    text: str
    value: str


def _css_escape(value: str) -> str:
    """把 DOM ``id`` 转义为 CSS 选择器 id（非字母数字统一反斜杠转义）。"""
    return re.sub(r"([^A-Za-z0-9_-])", r"\\\1", value)


class EngineRefMap:
    """ref ↔ 元素 id ↔ DOM 节点 ↔ CSS 选择器的确定性映射表。"""

    def __init__(self) -> None:
        self._entries: dict[str, RefResolution] = {}
        self._previous_refs: set[str] = set()
        self._generation = 0
        self._snapshot_url: str | None = None

    # ---- 查询 ---------------------------------------------------------

    @property
    def generation(self) -> int:
        """当前快照代次（每次刷新 +1）。"""
        return self._generation

    @property
    def snapshot_url(self) -> str | None:
        """生成当前 ref 快照时的页面 URL。"""
        return self._snapshot_url

    @property
    def refs(self) -> list[str]:
        """当前快照中全部合法 ref（按登记顺序）。"""
        return list(self._entries)

    def resolve(self, ref: str, current_url: str | None = None) -> tuple[str, RefResolution | None]:
        """解析 ref，返回 ``(状态, 解析结果)``。

        状态：``valid``（可操作）/ ``stale``（过期）/ ``invalid``（无效）。
        过期=曾在历史快照中出现但当前已失效；无效=从未出现过。
        """
        if ref not in self._entries:
            if ref in self._previous_refs:
                return _RESOLVE_STALE, None
            return _RESOLVE_INVALID, None
        if (
            current_url is not None
            and self._snapshot_url is not None
            and current_url != self._snapshot_url
        ):
            return _RESOLVE_STALE, None
        return _RESOLVE_VALID, self._entries[ref]

    # ---- 刷新 ---------------------------------------------------------

    def refresh(self, graph: SemanticGraph, snapshot: DomSnapshot | None = None) -> None:
        """随语义图生成刷新映射表：作废旧 ref、登记新 ref（§7.8 策略 B）。

        :param graph: 新语义图（元素 ref/dom_node_id 为登记来源）。
        :param snapshot: 与图同源抓取的 DOM 快照（选择器推导来源）。
        """
        self._previous_refs = set(self._entries)
        self._generation += 1
        self._snapshot_url = (snapshot.url if snapshot else None) or graph.page.url
        nodes, _ = self._index_nodes(snapshot)
        entries: dict[str, RefResolution] = {}
        for element in graph.elements:
            node = nodes.get(element.dom_node_id)
            entries[element.ref] = RefResolution(
                ref=element.ref,
                element_id=element.id,
                dom_node_id=element.dom_node_id,
                selector=self._selector_for(element, node),
                tag=element.tag,
                role=element.role,
                text=element.state.text,
                value=element.state.value,
            )
        self._entries = entries

    # ---- 内部 ---------------------------------------------------------

    @staticmethod
    def _index_nodes(
        snapshot: DomSnapshot | None,
    ) -> tuple[dict[str, ElementNode], dict[str, str]]:
        """构建节点索引（id → 节点）与快照树父指针。"""
        nodes: dict[str, ElementNode] = {}
        parents: dict[str, str] = {}
        if snapshot is None or snapshot.root is None:
            return nodes, parents
        root = snapshot.root
        nodes[root.id] = root
        stack = [(child, root.id) for child in reversed(root.children)]
        while stack:
            node, parent_id = stack.pop()
            nodes[node.id] = node
            parents[node.id] = parent_id
            for child in reversed(node.children):
                stack.append((child, node.id))
        return nodes, parents

    @classmethod
    def _selector_for(cls, element: Element, node: ElementNode | None) -> str:
        """推导 CSS 选择器：``#dom_id`` → 真实 DOM 索引路径 → ``:has-text`` → ``input[value]``。

        定位优先级（从可靠到兜底）：
        1. DOM ``id``（``#<id>``）最精确。
        2. 快照节点携带的**真实 DOM 索引路径**（``nth-of-type``，含被过滤的
           中间容器）——由爬取端从真实 DOM 祖先生成，不受快照树过滤影响，
           唯一且精确定位；优先于文本定位可避免重复文本的 strict 冲突。
        3. 元素可见文本（``tag:has-text("文本")``）——无 id/无路径时的
           兜底（Playwright :has-text 子串匹配；文本重复时可能歧义）。
        4. ``<input>`` 元素按稳定的 value 属性定位（submit/button 按钮标签在
           value 中，无子文本）。
        """
        if node is not None and node.dom_id:
            return f"#{_css_escape(node.dom_id)}"
        if node is not None and node.path:
            return node.path
        if node is None:
            return element.tag or element.role
        text = (element.state.text or "").strip()
        tag = element.tag or element.role
        if text and cls._text_safe(text):
            return f'{tag}:has-text("{cls._escape_text(text)}")'
        value = (node.value or element.state.value or "").strip()
        if node.tag == "input" and value and cls._text_safe(value):
            return f'input[value="{cls._escape_text(value)}"]'
        return element.tag or element.role

    @staticmethod
    def _text_safe(text: str) -> bool:
        """文本是否适合用于 :has-text 定位（无换行/引号等破坏选择器的字符）。"""
        return "\n" not in text and '"' not in text and "\\" not in text

    @staticmethod
    def _escape_text(text: str) -> str:
        """转义文本中的双引号（防御 :has-text 内嵌引号破坏）。"""
        return text.replace('"', '\\"')


__all__ = [
    "EngineRefMap",
    "RefResolution",
    "_RESOLVE_VALID",
    "_RESOLVE_STALE",
    "_RESOLVE_INVALID",
]
