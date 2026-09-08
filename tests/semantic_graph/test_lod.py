"""M4 任务 4.3：LOD 四维裁剪（深度/广度/属性/关联）与 LOD-0~3 预置组合。

同一页面四档 LOD 输出符合维度定义（深度/广度/属性/关联逐级增强，§9.5）。
"""

from __future__ import annotations

from snapshot_factory import SnapshotBuilder

from webops.semantic_graph import MockFiller, generate_semantic_graph


def _nested_snapshot():
    """带嵌套语义容器的页面：FORM F1（深度0）内含 FIELDSET GS1（深度1）。

    元素：用户名 label+input（层级0）、角色 label+select（层级1）。
    """
    b = SnapshotBuilder()
    form = b.node(
        "form",
        node_id="n-form",
        x=10,
        y=10,
        w=300,
        h=110,
        children=[
            b.node("span", text="用户名", node_id="n-user-label", x=10, y=20, w=50, h=18),
            b.node(
                "input",
                value="初始",
                node_id="n-username",
                dom_id="username",
                x=70,
                y=20,
                w=120,
                h=18,
            ),
            b.node(
                "fieldset",
                node_id="n-fs",
                x=10,
                y=50,
                w=280,
                h=60,
                children=[
                    b.node("span", text="角色", node_id="n-role-label", x=10, y=60, w=50, h=18),
                    b.node(
                        "select",
                        selected="管理员",
                        options=["管理员", "普通用户"],
                        node_id="n-role",
                        x=70,
                        y=60,
                        w=120,
                        h=18,
                    ),
                ],
            ),
        ],
    )
    return b.snapshot(body_children=[form], title="嵌套页")


def _filler():
    return MockFiller(
        purposes={"n-username": "用户名输入框", "n-role": "角色选择"},
        region_labels={"F1": "登录区", "GS1": "角色组"},
        related=[
            {"from_id": "n-user-label", "to_id": "n-username", "score": 0.9, "reason": "标签-控件"},
            {"from_id": "n-role-label", "to_id": "n-role", "score": 0.3, "reason": "弱关联"},
        ],
    )


class TestLodDimensions:
    """四维裁剪逐级增强（深度/广度/属性/关联，§9.5）。"""

    def _graph(self, lod):
        return generate_semantic_graph(_nested_snapshot(), lod=lod, filler=_filler())

    def test_element_count_grows_with_depth(self):
        counts = [len(self._graph(level).elements) for level in range(4)]
        assert counts[0] == 2  # LOD-0：只含直接候选（层级0）
        assert counts[1] == 4  # LOD-1+：含嵌套容器（层级1）内元素
        assert counts[2] == 4
        assert counts[3] == 4

    def test_region_depth_cropping(self):
        lod0 = self._graph(0)
        assert {region.id for region in lod0.regions} == {"F1"}  # 深度0
        lod1 = self._graph(1)
        assert {region.id for region in lod1.regions} == {"F1", "GS1"}

    def test_attributes_grow_with_lod(self):
        def username_value(level):
            graph = self._graph(level)
            return next(
                e for e in graph.elements if e.dom_node_id == "n-username"
            ).state.value

        def options(level):
            graph = self._graph(level)
            select = next(e for e in graph.elements if e.dom_node_id == "n-role")
            return select.options

        assert username_value(0) == ""  # minimal：仅 role+名
        assert username_value(1) == "初始"  # standard：含 value
        # LOD-0 深度裁剪不含层级1的 select（见 test_element_count_grows_with_depth）
        assert options(1) == []  # standard 清空选项
        assert options(2) == ["管理员", "普通用户"]  # rich：含相关文本/选项
        assert options(3) == ["管理员", "普通用户"]  # full

    def test_relations_grow_with_lod(self):
        def related_count(level):
            graph = self._graph(level)
            return sum(1 for edge in graph.edges if edge.type == "related-to")

        assert related_count(0) == 0  # none
        assert related_count(1) == 1  # high：只保留高分（0.9 ≥ 0.7）
        assert related_count(2) == 2  # all：含弱关联（0.3）
        assert related_count(3) == 2

    def test_structural_edges_kept_at_all_lods(self):
        for level in range(4):
            graph = self._graph(level)
            part_of = [edge for edge in graph.edges if edge.type == "part-of"]
            assert part_of  # 结构边始终保留（§9.5 ④ 只裁剪 related-to）

    def test_lod_spec_accepted(self):
        from webops.browser.models import LODSpec

        graph = generate_semantic_graph(
            _nested_snapshot(), lod=LODSpec.from_level(0), filler=_filler()
        )
        assert len(graph.elements) == 2


def _deep_nav_snapshot():
    """深层嵌套页面：FORM F1(depth0) → FIELDSET GS1(depth1) → FIELDSET GS2(depth2) → 深层链接。

    验证 §8.4「可交互 + 携带文本的元素必须进图」——深层容器内的可交互元素
    不因 LOD 深度裁剪而丢失（深度只裁剪语义容器骨架，不裁剪叶子元素）。
    """
    b = SnapshotBuilder()
    deep_link = b.node("a", text="Enterprise", node_id="n-enterprise", x=10, y=80, w=100, h=20)
    gs2 = b.node(
        "fieldset",
        node_id="n-gs2",
        x=10,
        y=50,
        w=200,
        h=60,
        children=[deep_link],
    )
    gs1 = b.node(
        "fieldset",
        node_id="n-gs1",
        x=10,
        y=30,
        w=240,
        h=90,
        children=[gs2],
    )
    form = b.node(
        "form",
        node_id="n-form",
        x=10,
        y=10,
        w=300,
        h=120,
        children=[gs1],
    )
    return b.snapshot(body_children=[form], title="深层导航页")


class TestDeepInteractiveKept:
    """§8.4 回归：深层容器内的可交互/文本元素在 LOD-1/2 必须保留。"""

    def _graph(self, lod):
        return generate_semantic_graph(_deep_nav_snapshot(), lod=lod, filler=MockFiller())

    def test_deep_interactive_element_kept_at_lod1_2(self):
        for lod in (1, 2, 3):
            graph = self._graph(lod)
            enterprise = [e for e in graph.elements if e.dom_node_id == "n-enterprise"]
            assert enterprise, f"LOD-{lod}: 深层可交互元素 Enterprise 被错误裁剪"
            assert enterprise[0].state.text == "Enterprise"
            # 深层容器骨架仍按深度裁剪（§9.5 ①）
            if lod == 1:
                assert {r.id for r in graph.regions} <= {"F1", "GS1"}

    def test_deep_text_in_serialized_graph(self):
        from webops.semantic_graph import serialize

        graph = self._graph(2)
        assert "Enterprise" in serialize(graph)


class TestLod3Full:
    """LOD-3：全量展开（深度/广度/属性/关联全部）。"""

    def test_full_output(self):
        graph = generate_semantic_graph(_nested_snapshot(), lod=3, filler=_filler())
        assert len(graph.elements) == 4
        assert {region.id for region in graph.regions} == {"F1", "GS1"}
        assert len([e for e in graph.edges if e.type == "related-to"]) == 2
