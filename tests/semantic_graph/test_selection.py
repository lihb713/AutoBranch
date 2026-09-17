"""M4 任务 2.1：候选元素筛选规则（§8.4）。

固定 HTML fixture（``snapshot_factory.login_snapshot`` 等）断言：可交互+携带文本
必进、语义容器作 REGION 骨架、纯定位 div/span 归属性、过滤（M1 已剔除隐藏，
本模块处理容器分类）。
"""

from __future__ import annotations

from autobranch.semantic_graph.selection import build_semantic_tree, classify
from snapshot_factory import SnapshotBuilder, login_snapshot, orders_snapshot

from autobranch.semantic_graph import run_programmatic


def _tree(snapshot):
    return build_semantic_tree(snapshot)


def _regions(tree):
    return {region.region_type: region for region in tree.regions}


class TestClassify:
    """§8.4 分类：container / interactive / text / pure。"""

    def test_container_classified(self):
        b = SnapshotBuilder()
        assert classify(b.node("form")) == "container"
        assert classify(b.node("table")) == "container"
        assert classify(b.node("nav")) == "container"
        assert classify(b.node("section")) == "container"

    def test_interactive_classified(self):
        b = SnapshotBuilder()
        assert classify(b.node("input")) == "interactive"
        assert classify(b.node("button")) == "interactive"
        assert classify(b.node("a", text="链接")) == "interactive"
        assert classify(b.node("select")) == "interactive"
        assert classify(b.node("textarea")) == "interactive"

    def test_text_bearing_classified(self):
        b = SnapshotBuilder()
        assert classify(b.node("span", text="¥98.00")) == "text"

    def test_pure_div_classified(self):
        b = SnapshotBuilder()
        assert classify(b.node("div")) == "pure"
        assert classify(b.node("span")) == "pure"


class TestLoginPageSelection:
    """登录页：候选集/区域骨架/归属（§8.4 ①②③）。"""

    def test_interactive_and_text_elements_included(self):
        tree = _tree(login_snapshot())
        texts = [element.state.text for element in tree.elements]
        roles = {element.role for element in tree.elements}
        # 输入框、按钮、链接、复选框 + 文本 span/label
        assert "textbox" in roles
        assert "button" in roles
        assert "link" in roles
        assert "checkbox" in roles
        assert "用户名" in texts
        assert "欢迎回来，张三" in texts  # 纯定位 div 内的 span 归并入图

    def test_containers_become_regions(self):
        regions = _regions(_tree(login_snapshot()))
        assert regions["form"].id == "F1"
        assert regions["nav"].id == "N1"
        assert regions["form"].depth == 0

    def test_pure_div_not_in_hierarchy(self):
        tree = _tree(login_snapshot())
        # 欢迎 span 直接归属文档（div 被归并，不占层级，§8.4 ③）
        greeting = tree.element(tree.children["root"][-1])
        assert greeting.state.text == "欢迎回来，张三"
        assert tree.owner.get(greeting.id) is None

    def test_text_recorded_as_attribute(self):
        tree = _tree(login_snapshot())
        username = next(e for e in tree.elements if e.dom_node_id == "n-username")
        assert username.state.text == ""
        label = next(e for e in tree.elements if e.dom_node_id == "n-user-label")
        assert label.state.text == "用户名"  # 文本是元素属性，不单独成节点

    def test_part_of_attribution(self):
        tree = _tree(login_snapshot())
        username = next(e for e in tree.elements if e.dom_node_id == "n-username")
        assert tree.owner[username.id] == "F1"  # 归属到 form 区域
        nav_link = next(e for e in tree.elements if e.dom_node_id == "n-orders")
        assert tree.owner[nav_link.id] == "N1"


class TestOrdersPageSelection:
    """订单页：表格框架作为区域骨架（§8.4 ②）。"""

    def test_table_framework_regions(self):
        regions = _regions(_tree(orders_snapshot()))
        assert "table" in regions
        assert "rowgroup" in regions
        assert "row" in regions
        assert regions["table"].id == "T1"

    def test_cells_and_buttons_are_elements(self):
        tree = _tree(orders_snapshot())
        roles = {element.role for element in tree.elements}
        assert "cell" in roles
        assert "column" in roles  # th 归一化（§8.3 ②）
        assert "button" in roles
        assert any(element.state.text == "¥98.00" for element in tree.elements)


class TestFiltering:
    """§8.4 ⑤：隐藏/零尺寸/aria-hidden 由 M1 剔除，M4 只处理容器分类。"""

    def test_m1_already_excludes_hidden(self):
        # M1 快照不含隐藏元素；M4 不再重复引入
        b = SnapshotBuilder()
        snapshot = b.snapshot(body_children=[b.node("span", text="可见文本")])
        tree = _tree(snapshot)
        assert [element.state.text for element in tree.elements] == ["可见文本"]

    def test_zero_sized_container_still_region_if_in_snapshot(self):
        # M1 会剔除零尺寸元素；此处验证 M4 不自行引入
        b = SnapshotBuilder()
        tree = _tree(b.snapshot(body_children=[b.node("div", text="")]))
        assert tree.elements == []
        assert tree.regions == []


class TestModulePipeline:
    """程序化阶段可独立跑通（run_programmatic）。"""

    def test_programmatic_result_shape(self):
        result = run_programmatic(login_snapshot())
        assert result.tree.elements
        assert result.tree.regions
        assert result.edges  # part-of 边
        assert result.ref_map.ref_to_element
        assert result.related_candidates

    def test_ids_unique(self):
        result = run_programmatic(login_snapshot())
        ids = [element.id for element in result.tree.elements]
        assert len(ids) == len(set(ids))
