"""M5 任务 3.x：ref 确定性解析（合法/无效/过期/随语义图刷新）。"""

from __future__ import annotations

from engine_helpers import make_graph, make_snapshot

from webops.browser import DomSnapshot, ElementNode, LODSpec
from webops.engine import EngineRefMap


class TestValidRef:
    """任务 3.1：合法 ref 解析到对应节点（确定性映射）。"""

    def test_valid_ref_resolves_to_element_and_selector(self):
        refmap = EngineRefMap()
        refmap.refresh(make_graph(value="admin"), make_snapshot(value="admin"))
        status, resolution = refmap.resolve("[1]", current_url="http://example.com/page")
        assert status == "valid"
        assert resolution.element_id == "E1"
        assert resolution.dom_node_id == "1"
        assert resolution.selector == "#username"
        assert resolution.value == "admin"

    def test_selector_uses_dom_id_priority(self):
        refmap = EngineRefMap()
        refmap.refresh(
            make_graph(dom_node_id="7"), make_snapshot(dom_id="login-btn", node_id="7")
        )
        status, resolution = refmap.resolve("[1]", current_url="http://example.com/page")
        assert resolution.selector == "#login-btn"


class TestInvalidRef:
    """任务 3.2：不在映射表中的 ref 被拒绝。"""

    def test_invalid_ref_rejected(self):
        refmap = EngineRefMap()
        refmap.refresh(make_graph(), make_snapshot())
        status, resolution = refmap.resolve("[99]", current_url="http://example.com/page")
        assert status == "invalid"
        assert resolution is None


class TestStaleRef:
    """任务 3.3/3.4：快照更新/页面状态变化后旧 ref 过期被拒。"""

    def test_old_ref_rejected_after_refresh(self):
        refmap = EngineRefMap()
        refmap.refresh(make_graph(), make_snapshot())
        # 新快照生成：元素变化，旧 ref 失效
        refmap.refresh(
            make_graph(ref="[2]", element_id="E2", dom_node_id="2"),
            make_snapshot(dom_id="password", node_id="2"),
        )
        assert refmap.generation == 2
        status, _ = refmap.resolve("[1]", current_url="http://example.com/page")
        assert status == "stale"
        # 新 ref 有效
        status, resolution = refmap.resolve("[2]", current_url="http://example.com/page")
        assert status == "valid"
        assert resolution.selector == "#password"
        # 从未出现过的 ref 仍是无效（而非过期）
        status, _ = refmap.resolve("[3]", current_url="http://example.com/page")
        assert status == "invalid"

    def test_refs_refresh_after_new_snapshot(self):
        refmap = EngineRefMap()
        refmap.refresh(make_graph(), make_snapshot())
        assert refmap.refs == ["[1]"]
        refmap.refresh(
            make_graph(ref="[2]", element_id="E2", dom_node_id="2"),
            make_snapshot(dom_id="password", node_id="2"),
        )
        assert refmap.refs == ["[2]"]

    def test_stale_on_page_navigation(self):
        refmap = EngineRefMap()
        refmap.refresh(make_graph(url="http://a/page"), make_snapshot(url="http://a/page"))
        # 导航到其他 URL → 旧 ref 过期
        status, _ = refmap.resolve("[1]", current_url="http://a/other")
        assert status == "stale"


class TestSelectorFallback:
    """选择器兜底：无 dom_id 节点 → 快照树标签路径。"""

    def test_tag_path_fallback(self):
        node = ElementNode(id="1", tag="input", role="textbox", dom_id="", depth=0)
        root = ElementNode(id="root", tag="root", role="document", children=[node])
        snapshot = DomSnapshot(
            url="http://x",
            title="t",
            lod=LODSpec.from_level(2),
            root=root,
            elements=[node],
        )
        refmap = EngineRefMap()
        refmap.refresh(make_graph(url="http://x"), snapshot)
        status, resolution = refmap.resolve("[1]", current_url="http://x")
        assert status == "valid"
        assert resolution.selector == "body > input"

    def test_text_based_selector_for_navigation_link(self):
        """无 dom_id 但有可见文本的链接 → ``tag:has-text("文本")``（§7.8 定位兜底）。

        回归：深层导航链接（如 opencode.ai 的 Go/Enterprise）不能被推导成
        错误的 ``body > a``（快照树路径不精确），应基于文本可靠定位。
        """
        node = ElementNode(
            id="7", tag="a", role="link", dom_id="", text="Enterprise", depth=7
        )
        root = ElementNode(id="root", tag="root", role="document", children=[node])
        snapshot = DomSnapshot(
            url="http://x",
            title="t",
            lod=LODSpec.from_level(3),
            root=root,
            elements=[node],
        )
        graph = make_graph(url="http://x", tag="a", role="link", text="Enterprise", dom_node_id="7")
        refmap = EngineRefMap()
        refmap.refresh(graph, snapshot)
        status, resolution = refmap.resolve("[1]", current_url="http://x")
        assert status == "valid"
        assert resolution.selector == 'a:has-text("Enterprise")'
