"""M4 任务 2.4：程序化值读取（value/checked/disabled/visible/text/selected/options）。

fixture 断言各状态字段与 select 选项实时读取（§8.3 ④、§9.5 程序化值实时读取）。
"""

from __future__ import annotations

from autobranch.semantic_graph.values import read_state
from snapshot_factory import SnapshotBuilder, login_snapshot

from autobranch.semantic_graph import run_programmatic


class TestReadState:
    """§8.3 ④：从 DOM 快照节点读取程序化状态。"""

    def test_all_state_fields(self):
        b = SnapshotBuilder()
        node = b.node(
            "input",
            value="admin",
            checked=False,
            disabled=True,
            selected="",
            text="",
        )
        state = read_state(node)
        assert state.value == "admin"
        assert state.checked is False
        assert state.disabled is True
        assert state.visible is True
        assert state.selected == ""

    def test_checkbox_checked_state(self):
        b = SnapshotBuilder()
        node = b.node("input", role="checkbox", checked=True, value="on")
        state = read_state(node)
        assert state.checked is True
        assert state.value == "on"


class TestValuesInPipeline:
    """程序化值进入语义图元素（§9.5 实时读取）。"""

    def test_login_programmatic_values(self):
        result = run_programmatic(login_snapshot())
        by_node = {element.dom_node_id: element for element in result.tree.elements}
        remember = by_node["n-remember"]
        assert remember.role == "checkbox"
        assert remember.state.checked is True
        assert remember.state.text == ""

    def test_select_options_and_selected(self):
        b = SnapshotBuilder()
        select = b.node(
            "select",
            selected="管理员",
            options=["管理员", "普通用户", "访客"],
            node_id="n-role",
        )
        snapshot = b.snapshot(body_children=[select])
        result = run_programmatic(snapshot)
        element = result.tree.elements[0]
        assert element.role == "select"  # listbox 归一化
        assert element.state.selected == "管理员"
        assert element.options == ["管理员", "普通用户", "访客"]

    def test_text_and_value_fields(self):
        result = run_programmatic(login_snapshot())
        by_node = {element.dom_node_id: element for element in result.tree.elements}
        label = by_node["n-user-label"]
        assert label.state.text == "用户名"
        username = by_node["n-username"]
        assert username.state.value == ""
        login_btn = by_node["n-login"]
        assert login_btn.state.text == "登录"
