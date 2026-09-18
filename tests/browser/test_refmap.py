"""refmap 选择器生成单测：通用、无歧义、不依赖脆弱的标签路径。

根因：旧标签路径算法在快照树中被过滤的中间容器（如 GitHub 登录表单外的 div）
处断裂，生成 ``body > form > input`` / ``body > input`` 这类匹配不到真实 DOM 的
选择器，导致点击 30s 超时。现改为爬取端携带真实 DOM 的 ``nth-of-type`` 索引路径，
对任意深度的元素都能精确定位。
"""

from __future__ import annotations

from autobranch.plugins.browser.driver.models import ElementNode
from autobranch.plugins.browser.refmap import EngineRefMap
from autobranch.plugins.browser.semantic_graph.models import Element, ElementState


def _node(
    tag: str,
    dom_id: str = "",
    *,
    depth: int = 3,
    value: str = "",
    text: str = "",
    path: str = "",
) -> ElementNode:
    return ElementNode(
        id=dom_id or tag,
        tag=tag,
        role="",
        dom_id=dom_id,
        depth=depth,
        text=text,
        value=value,
        path=path,
    )


def _element(ref: str, role: str, tag: str, *, value: str = "", text: str = "") -> Element:
    return Element(
        id=f"E{ref.strip('[]')}",
        ref=ref,
        role=role,
        tag=tag,
        state=ElementState(value=value, text=text),
    )


def _selector(element: Element, node: ElementNode) -> str:
    return EngineRefMap._selector_for(element, node)


def test_submit_input_uses_value_selector():
    """submit 按钮：无 id、无文本 → 用稳定的 value 属性定位。"""
    node = _node("input", depth=3, value="Sign in")
    element = _element("[10]", "button", "input", value="Sign in")
    assert _selector(element, node) == 'input[value="Sign in"]'


def test_id_selector_still_preferred():
    """有 DOM id 的元素仍优先 ``#id``（不因 value 定位而退化）。"""
    node = _node("input", dom_id="login_field", value="", depth=3)
    element = _element("[6]", "textbox", "input")
    assert _selector(element, node) == "#login_field"


def test_text_selector_still_preferred():
    """按钮有可见文本仍优先 ``:has-text``。"""
    node = _node("button", depth=3)
    element = _element("[12]", "button", "button", text="Continue with Google")
    assert _selector(element, node) == 'button:has-text("Continue with Google")'


def test_path_preferred_over_ambiguous_text():
    """有精确索引路径时优先路径而非 ``:has-text``——避免重复文本 strict 冲突。"""
    path = "body > nav:nth-of-type(1) > a:nth-of-type(3)"
    node = _node("a", depth=4, path=path, text="Usage")
    element = _element("[8]", "link", "a", text="Usage")
    assert _selector(element, node) == path


def test_indexed_path_fallback_for_filtered_ancestors():
    """无 id/无文本/无 value 的元素 → 用快照携带的真实 DOM 索引路径。

    中间容器（div）被过滤出快照树时，索引路径仍含之，能精确匹配真实 DOM。
    """
    path = (
        "body > main:nth-of-type(1) > div:nth-of-type(1) > "
        "form:nth-of-type(1) > button:nth-of-type(1)"
    )
    node = _node("button", depth=4, path=path)
    element = _element("[7]", "button", "button")
    assert _selector(element, node) == path


def test_no_path_falls_back_to_tag():
    """快照未携带路径（异常兜底）时退化为标签选择器。"""
    node = _node("input", depth=3)
    element = _element("[99]", "textbox", "input")
    assert _selector(element, node) == "input"
