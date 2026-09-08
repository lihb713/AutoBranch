"""M4 序列化方位标注测试（§8.3 ③ 扩展 / §7.6）。

带 viewport 的语义图，元素行/区域头输出稳定方位词（如 `(页面top-right)`），
供 LLM 理解「右上角 / 底部」等位置指令；无 viewport 时不输出（不破坏旧行为）。
"""

from __future__ import annotations

from snapshot_factory import build

from webops.semantic_graph import MockFiller, generate_semantic_graph, serialize

VIEWPORT = {"width": 900, "height": 600}


def _login_form_snapshot():
    b = build()
    form = b.node(
        "form",
        node_id="n-form",
        x=100,
        y=20,
        w=300,
        h=100,
        children=[
            b.node("span", text="用户名", node_id="n-label", x=110, y=30, w=50, h=18),
            b.node(
                "input",
                value="",
                node_id="n-user",
                dom_id="username",
                x=170,
                y=30,
                w=120,
                h=18,
            ),
            b.node(
                "button",
                text="登录",
                node_id="n-btn",
                dom_id="login-btn",
                x=250,
                y=60,
                w=80,
                h=30,
            ),
        ],
    )
    return b.snapshot(body_children=[form], viewport=VIEWPORT)


def test_serialize_contains_page_quadrant():
    graph = generate_semantic_graph(_login_form_snapshot(), lod=3, filler=MockFiller())
    text = serialize(graph)
    # 登录按钮行（purpose 未填时显示 text="登录"）应带方位标注
    # 按钮中心 x=290, y=75 → 左区/顶部 → top-left
    btn_line = next(line for line in text.splitlines() if 'text="登录"' in line)
    assert "页面top-left" in btn_line


def test_serialize_region_has_quadrant():
    graph = generate_semantic_graph(_login_form_snapshot(), lod=3, filler=MockFiller())
    text = serialize(graph)
    # FORM 区域：中心 x=250, y=70 → 左区/顶部 → top-left
    assert "REGION FORM" in text
    assert "页面top-left" in text


def test_no_viewport_no_quadrant():
    b = build()
    form = b.node(
        "form",
        node_id="n-form",
        x=100,
        y=20,
        w=300,
        h=100,
        children=[
            b.node(
                "button",
                text="登录",
                node_id="n-btn",
                dom_id="login-btn",
                x=250,
                y=60,
                w=80,
                h=30,
            )
        ],
    )
    # 无 viewport
    graph = generate_semantic_graph(
        b.snapshot(body_children=[form]), lod=3, filler=MockFiller()
    )
    text = serialize(graph)
    btn_line = next(line for line in text.splitlines() if 'text="登录"' in line)
    assert "页面top" not in btn_line  # 无 viewport 不输出方位
