"""DOM 原始爬取（M1 spec §5.4、契约 §8.3/§8.4/§8.9）。

``DomProbe.crawl`` 在页面内注入一段脚本遍历主文档，产出节点树/role/可见性/
包围盒/程序化值（value/checked/disabled/selected/options/text）快照，供 M4
语义图程序化阶段使用。

筛选与边界（§8.4 ⑤、§8.9）：
- 剔除隐藏（display:none / visibility:hidden）、零尺寸、``aria-hidden`` 元素。
- 只覆盖主文档，不进入 iframe。
- 不处理懒加载/虚拟滚动/动态渲染。
- LOD 深度维度控制语义容器嵌套层数（§9.5），-1 表示不限。
"""

from __future__ import annotations

from autobranch.plugins.browser.driver.driver import BrowserDriver
from autobranch.plugins.browser.driver.models import (
    Bounds,
    DomSnapshot,
    ElementNode,
    LODSpec,
    PageRef,
)

_CRAWL_JS = r"""
() => {
  const ROLE_MAP = {
    'a': 'link', 'button': 'button', 'select': 'listbox', 'textarea': 'textbox',
    'table': 'table', 'tr': 'row', 'td': 'cell', 'th': 'columnheader',
    'ul': 'list', 'ol': 'list', 'li': 'listitem', 'dl': 'list', 'dt': 'term', 'dd': 'definition',
    'form': 'form', 'nav': 'navigation', 'section': 'region', 'dialog': 'dialog',
    'fieldset': 'group', 'header': 'banner', 'footer': 'contentinfo', 'main': 'main',
    'aside': 'complementary', 'p': 'paragraph', 'label': 'label', 'img': 'img',
    'h1': 'heading', 'h2': 'heading', 'h3': 'heading', 'h4': 'heading',
    'h5': 'heading', 'h6': 'heading', 'span': 'generic',
  };
  const CONTAINER_TAGS = new Set([
    'form', 'table', 'ul', 'ol', 'dl', 'nav', 'section', 'dialog',
    'fieldset', 'header', 'footer', 'main', 'aside', 'tr', 'tbody', 'thead', 'tfoot',
  ]);
  const INTERACTIVE_TAGS = new Set(['input', 'button', 'a', 'select', 'textarea']);
  const SKIP_TAGS = new Set([
    'html', 'body', 'head', 'script', 'style', 'noscript', 'link', 'meta',
    'title', 'br', 'hr', 'option', 'iframe',
  ]);

  let nextId = 1;

  function roleOf(el) {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === 'input') {
      const t = (el.getAttribute('type') || 'text').toLowerCase();
      if (t === 'checkbox') return 'checkbox';
      if (t === 'radio') return 'radio';
      if (t === 'number') return 'spinbutton';
      if (t === 'range') return 'slider';
      if (t === 'submit' || t === 'button' || t === 'reset') return 'button';
      return 'textbox';
    }
    return ROLE_MAP[tag] || tag;
  }

  function ownText(el) {
    let text = '';
    for (const node of el.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) text += node.textContent;
    }
    return text.trim();
  }

  function nthIndex(el) {
    const tag = el.tagName.toLowerCase();
    const parent = el.parentElement;
    if (!parent) return 1;
    let n = 1;
    for (const sib of parent.children) {
      if (sib === el) break;
      if (sib.tagName.toLowerCase() === tag) n++;
    }
    return n;
  }

  function indexedPath(el) {
    // 真实 DOM 的索引化路径（nth-of-type），含被过滤的中间容器，可精确定位。
    const parts = [];
    let cur = el;
    while (cur && cur !== document.body) {
      parts.unshift(`${cur.tagName.toLowerCase()}:nth-of-type(${nthIndex(cur)})`);
      cur = cur.parentElement;
    }
    parts.unshift('body');
    return parts.join(' > ');
  }

  function textOf(el) {
    if (el.children.length === 0) return (el.textContent || '').trim();
    return ownText(el);
  }

  function shouldInclude(el, role, tag) {
    if (el.getAttribute('role')) return true;
    if (INTERACTIVE_TAGS.has(tag)) return true;
    if (CONTAINER_TAGS.has(tag)) return true;
    if (textOf(el) !== '') return true;
    return false;
  }

  function buildNode(el, role, depth) {
    const tag = el.tagName.toLowerCase();
    const rect = el.getBoundingClientRect();
    const node = {
      id: String(nextId++),
      tag: tag,
      role: role,
      dom_id: el.id || '',
      depth: depth,
      text: textOf(el),
      visible: true,
      bounds: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
      path: indexedPath(el),
      children: [],
    };
    if (tag === 'select') {
      node.value = el.value || '';
      node.selected = el.options[el.selectedIndex]
        ? (el.options[el.selectedIndex].textContent || '').trim() : '';
      node.options = Array.from(el.options).map((o) => (o.textContent || '').trim());
      node.disabled = el.disabled;
    } else if (tag === 'input') {
      const t = (el.getAttribute('type') || 'text').toLowerCase();
      if (t === 'checkbox' || t === 'radio') {
        node.checked = el.checked;
        node.value = el.value || '';
      } else {
        node.value = el.value || '';
      }
      node.disabled = el.disabled;
    } else if (tag === 'textarea') {
      node.value = el.value || '';
      node.disabled = el.disabled;
    } else {
      node.disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
    }
    return node;
  }

  function walk(el, inheritedHidden, depth, lodDepth) {
    const tag = el.tagName.toLowerCase();
    const isSkip = SKIP_TAGS.has(tag);
    const cs = window.getComputedStyle(el);
    const hidden = inheritedHidden
      || el.getAttribute('aria-hidden') === 'true'
      || cs.display === 'none'
      || cs.visibility === 'hidden';
    const rect = el.getBoundingClientRect();
    const zero = !isSkip && rect.width === 0 && rect.height === 0;
    const role = roleOf(el);
    const atLimit = lodDepth >= 0 && depth >= lodDepth;

    const descendants = [];
    if (!atLimit) {
      for (const child of el.children) {
        descendants.push(...walk(child, hidden, depth + 1, lodDepth));
      }
    }

    if (isSkip) return descendants;
    if (hidden || zero) return descendants;

    let node = null;
    if ((lodDepth < 0 || depth <= lodDepth) && shouldInclude(el, role, tag)) {
      node = buildNode(el, role, depth);
    }
    if (node) {
      node.children = descendants;
      return [node];
    }
    return descendants;
  }

  return {
    url: window.location.href,
    title: document.title || '',
    viewport: { width: window.innerWidth, height: window.innerHeight },
    nodes: walk(document.body, false, -1, __LOD_DEPTH__),
  };
}
"""


def _build_node(data: dict) -> ElementNode:
    bounds_data = data.get("bounds")
    return ElementNode(
        id=data["id"],
        tag=data["tag"],
        role=data["role"],
        dom_id=data.get("dom_id", ""),
        text=data.get("text", ""),
        value=data.get("value", ""),
        checked=data.get("checked"),
        disabled=data.get("disabled", False),
        selected=data.get("selected", ""),
        options=list(data.get("options") or []),
        visible=data.get("visible", True),
        bounds=Bounds(**bounds_data) if bounds_data else None,
        depth=data.get("depth", 0),
        path=data.get("path", ""),
        children=[_build_node(c) for c in data.get("children") or []],
    )


def _flatten(nodes: list[ElementNode]) -> list[ElementNode]:
    result: list[ElementNode] = []
    for node in nodes:
        result.append(node)
        result.extend(_flatten(node.children))
    return result


class DomProbe:
    """DOM 爬取探针（M1 spec §5.4）。

    通过 ``BrowserDriver`` 解析页面引用后注入脚本爬取；无效引用抛
    ``PageRefError``（程序侧），浏览器崩溃/context 关闭抛
    ``FatalBrowserError``。
    """

    def __init__(self, driver: BrowserDriver) -> None:
        self._driver = driver

    def crawl(self, page_ref: PageRef, lod: LODSpec | None = None) -> DomSnapshot:
        """爬取指定页面，返回结构化快照（节点树/role/可见性/包围盒/程序化值）。"""
        lod = lod or LODSpec.from_level(3)
        page = self._driver._resolve_page(page_ref)
        data = page.evaluate(_CRAWL_JS.replace("__LOD_DEPTH__", str(lod.depth)))
        top_nodes = [_build_node(n) for n in data.get("nodes") or []]
        root = ElementNode(
            id="root",
            tag="root",
            role="document",
            children=top_nodes,
        )
        return DomSnapshot(
            url=data.get("url", page.url),
            title=data.get("title", ""),
            lod=lod,
            root=root,
            elements=_flatten(top_nodes),
            viewport=data.get("viewport") or {},
        )
