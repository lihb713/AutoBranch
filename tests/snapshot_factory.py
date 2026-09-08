"""DOM 快照构造器（M4 测试夹具，任务 1.3）。

用纯 Python 构造 ``DomSnapshot`` 树，模拟 M1 爬取产物（对齐 M1 spec §5.4/§5.5），
使 M4 程序化阶段可完全离线测试（不依赖真实浏览器与 LLM）。
"""

from __future__ import annotations

from webops.browser.models import Bounds, DomSnapshot, ElementNode, LODSpec

# 与 M1 ``roleOf`` 对齐的默认 role（M4 侧再归一化 listbox→select / columnheader→column）
DEFAULT_ROLE: dict[str, str] = {
    "a": "link",
    "button": "button",
    "select": "listbox",
    "textarea": "textbox",
    "table": "table",
    "tr": "row",
    "td": "cell",
    "th": "columnheader",
    "ul": "list",
    "ol": "list",
    "li": "listitem",
    "dl": "list",
    "form": "form",
    "nav": "navigation",
    "section": "region",
    "dialog": "dialog",
    "fieldset": "group",
    "span": "generic",
    "p": "paragraph",
    "div": "generic",
    "label": "label",
    "input": "textbox",
    "thead": "rowgroup",
    "tbody": "rowgroup",
    "tfoot": "rowgroup",
}


class SnapshotBuilder:
    """构造带自增 id 的 DOM 快照树（``N1``、``N2``...）。"""

    def __init__(self) -> None:
        self._counter = 0

    def node(
        self,
        tag: str,
        role: str | None = None,
        text: str = "",
        value: str = "",
        checked: bool | None = None,
        disabled: bool = False,
        selected: str = "",
        options: list[str] | None = None,
        dom_id: str = "",
        node_id: str | None = None,
        x: float = 0.0,
        y: float = 0.0,
        w: float = 0.0,
        h: float = 0.0,
        children: list[ElementNode] | None = None,
    ) -> ElementNode:
        """构造一个节点（bounds 恒为给定的矩形，可见性恒真）。"""
        self._counter += 1
        return ElementNode(
            id=node_id or f"N{self._counter}",
            tag=tag,
            role=role or DEFAULT_ROLE.get(tag, "generic"),
            dom_id=dom_id,
            text=text,
            value=value,
            checked=checked,
            disabled=disabled,
            selected=selected,
            options=list(options or []),
            visible=True,
            bounds=Bounds(x=x, y=y, w=w, h=h),
            depth=0,
            children=list(children or []),
        )

    def snapshot(
        self,
        body_children: list[ElementNode] | None = None,
        title: str = "测试页",
        url: str = "https://example.com/test",
        viewport: dict[str, int] | None = None,
    ) -> DomSnapshot:
        """构造完整快照：document 根 + 扁平 elements 列表。"""
        children = list(body_children or [])
        root = ElementNode(
            id="root",
            tag="root",
            role="document",
            children=children,
        )

        def flatten(nodes: list[ElementNode]) -> list[ElementNode]:
            result: list[ElementNode] = []
            for node in nodes:
                result.append(node)
                result.extend(flatten(node.children))
            return result

        return DomSnapshot(
            url=url,
            title=title,
            lod=LODSpec.from_level(3),
            root=root,
            elements=flatten(children),
            viewport=viewport or {},
        )


def build() -> SnapshotBuilder:
    """便捷入口。"""
    return SnapshotBuilder()


def login_snapshot() -> DomSnapshot:
    """登录页快照（与 ``tests/fixtures/sg_login.html`` 同构，带确定 bounds）。

    结构：FORM F1（用户名/密码 span+input、记住我 checkbox、登录按钮、忘记密码链接）
    + NAV N1（两个链接）+ 文档级文本 span（div 纯定位被归并）。
    """
    b = SnapshotBuilder()
    form = b.node(
        "form",
        node_id="n-form",
        dom_id="login-form",
        x=10,
        y=10,
        w=320,
        h=130,
        children=[
            b.node("span", text="用户名", node_id="n-user-label", x=10, y=20, w=50, h=18),
            b.node(
                "input",
                value="",
                dom_id="username",
                node_id="n-username",
                x=70,
                y=20,
                w=120,
                h=18,
            ),
            b.node("span", text="密码", node_id="n-pass-label", x=10, y=48, w=50, h=18),
            b.node(
                "input",
                value="",
                dom_id="password",
                node_id="n-password",
                x=70,
                y=48,
                w=120,
                h=18,
            ),
            b.node(
                "label",
                text="记住我",
                node_id="n-remember-label",
                x=10,
                y=76,
                w=60,
                h=18,
                children=[
                    b.node(
                        "input",
                        checked=True,
                        role="checkbox",
                        dom_id="remember",
                        node_id="n-remember",
                        x=10,
                        y=78,
                        w=12,
                        h=12,
                    )
                ],
            ),
            b.node(
                "button",
                text="登录",
                node_id="n-login",
                dom_id="login-btn",
                x=70,
                y=104,
                w=80,
                h=22,
            ),
            b.node(
                "a",
                text="忘记密码",
                node_id="n-forgot",
                dom_id="forgot",
                x=160,
                y=104,
                w=90,
                h=22,
            ),
        ],
    )
    nav = b.node(
        "nav",
        node_id="n-nav",
        x=10,
        y=160,
        w=320,
        h=30,
        children=[
            b.node("a", text="订单列表", node_id="n-orders", x=10, y=165, w=70, h=20),
            b.node("a", text="报表中心", node_id="n-report", x=90, y=165, w=70, h=20),
        ],
    )
    greeting = b.node("span", text="欢迎回来，张三", node_id="n-greeting", x=10, y=205, w=120, h=18)
    return b.snapshot(
        body_children=[form, nav, greeting],
        title="登录页",
        url="https://example.com/login",
    )


def orders_snapshot() -> DomSnapshot:
    """订单列表快照（与 ``tests/fixtures/sg_orders.html`` 同构，带确定 bounds）。

    结构：TABLE T1（表头行 column×5 + 两行数据，每行 4 个文本 cell + 1 个批准按钮）。
    """
    b = SnapshotBuilder()

    def header_row(y: float) -> ElementNode:
        return b.node(
            "tr",
            node_id="n-hrow",
            x=10,
            y=y,
            w=420,
            h=20,
            children=[
                b.node("th", text="订单号", node_id="n-h-order", x=10, y=y, w=80, h=20),
                b.node("th", text="客户", node_id="n-h-customer", x=90, y=y, w=80, h=20),
                b.node("th", text="金额", node_id="n-h-amount", x=170, y=y, w=80, h=20),
                b.node("th", text="状态", node_id="n-h-status", x=250, y=y, w=80, h=20),
                b.node("th", text="操作", node_id="n-h-action", x=330, y=y, w=80, h=20),
            ],
        )

    def data_row(
        y: float, order: str, customer: str, amount: str, status: str, row_id: str
    ) -> ElementNode:
        return b.node(
            "tr",
            node_id=row_id,
            x=10,
            y=y,
            w=420,
            h=20,
            children=[
                b.node("td", text=order, node_id=f"{row_id}-o", x=10, y=y, w=80, h=20),
                b.node("td", text=customer, node_id=f"{row_id}-c", x=90, y=y, w=80, h=20),
                b.node("td", text=amount, node_id=f"{row_id}-a", x=170, y=y, w=80, h=20),
                b.node("td", text=status, node_id=f"{row_id}-s", x=250, y=y, w=80, h=20),
                b.node("button", text="批准", node_id=f"{row_id}-btn", x=330, y=y, w=60, h=20),
            ],
        )

    table = b.node(
        "table",
        node_id="n-table",
        dom_id="orders",
        x=10,
        y=10,
        w=420,
        h=90,
        children=[
            b.node(
                "thead",
                node_id="n-thead",
                x=10,
                y=10,
                w=420,
                h=20,
                children=[header_row(10)],
            ),
            b.node(
                "tbody",
                node_id="n-tbody",
                x=10,
                y=30,
                w=420,
                h=60,
                children=[
                    data_row(30, "ORD-001", "甲公司", "¥98.00", "待审批", "n-r1"),
                    data_row(50, "ORD-002", "乙公司", "¥152.00", "待审批", "n-r2"),
                ],
            ),
        ],
    )
    return b.snapshot(
        body_children=[table],
        title="订单列表",
        url="https://orders.example.com/list",
    )
