"""程序化值读取（契约 §8.3 ④、§9.5）。

value/checked/disabled/visible/text/selected/options 由 M1 爬取时实时读取，
本模块把它们从快照节点复制进语义图元素，保证每次生成反映最新页面状态。
"""

from __future__ import annotations

from autobranch.plugins.browser.driver.models import ElementNode
from autobranch.plugins.browser.semantic_graph.models import ElementState


def read_state(node: ElementNode) -> ElementState:
    """从 DOM 快照节点读取程序化状态（§8.3 ④ 实时值）。"""
    return ElementState(
        value=node.value,
        checked=node.checked,
        disabled=node.disabled,
        visible=node.visible,
        text=node.text,
        selected=node.selected,
    )
