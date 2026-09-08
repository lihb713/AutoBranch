"""M4 任务 5.1/5.3：层次树序列化（REGION 头、元素行、文本承载元素、part-of 缩进、
value-of 并列、related-to 括号标注、兄弟视觉顺序）与完整示例快照（§7.6）。

引擎对象模型 → LLM 层次树文本（§7.6.2/§7.6.3/§7.6.4）。
"""

from __future__ import annotations

from snapshot_factory import login_snapshot, orders_snapshot

from webops.semantic_graph import MockFiller, generate_semantic_graph, serialize


def _login_form_graph():
    filler = MockFiller(
        purposes={
            "n-user-label": "用户名",
            "n-username": "用户名输入框",
            "n-pass-label": "密码",
            "n-password": "密码输入框",
            "n-remember-label": "记住我",
            "n-remember": "记住我",
            "n-login": "登录按钮",
            "n-forgot": "忘记密码链接",
        },
        region_labels={"F1": "登录区"},
        related=[
            {"from_id": "n-user-label", "to_id": "n-username", "score": 0.9,
             "reason": "这是用户名的标签", "confidence": "explicit"},
            {"from_id": "n-pass-label", "to_id": "n-password", "score": 0.9,
             "reason": "这是密码的标签", "confidence": "explicit"},
        ],
    )
    return generate_semantic_graph(login_snapshot(), scope="F1", filler=filler)


def _orders_graph():
    purposes = {f"n-h-{k}": v for k, v in
                {"order": "订单号", "customer": "客户", "amount": "金额",
                 "status": "状态", "action": "操作"}.items()}
    for i in (1, 2):
        purposes.update({f"n-r{i}-{k}": v for k, v in
                         {"o": "订单号", "c": "客户", "a": "金额", "s": "状态"}.items()})
    purposes["n-r1-btn"] = "批准"
    purposes["n-r2-btn"] = "批准"
    filler = MockFiller(
        purposes=purposes,
        region_labels={"T1": "订单列表", "G1": "表头区", "G2": "表体区",
                       "R1": "表头行", "R2": "订单行1", "R3": "订单行2"},
    )
    return generate_semantic_graph(orders_snapshot(), filler=filler)


class TestLoginSnapshot:
    """5.3：登录页序列化快照（对照契约 §7.6.4 登录页示例）。"""

    def test_login_snapshot_text(self):
        expected = "\n".join(
            [
                "PAGE: 登录页  URL=https://example.com/login",
                "",
                "REGION FORM F1 登录区",
                '  generic [1] 用户名="用户名"',
                '  FIELD [2] textbox "用户名输入框" value=""  (related-to: "用户名" 0.9·左侧邻近)',
                '  generic [3] 密码="密码"',
                '  FIELD [4] textbox "密码输入框" value=""  (related-to: "密码" 0.9·左侧邻近)',
                '  label [5] 记住我="记住我"',
                '  CHECK [6] "记住我" checked',
                '  ACTOR [7] button "登录按钮" text="登录"',
                '  LINK [8] "忘记密码链接" text="忘记密码"',
            ]
        )
        assert serialize(_login_form_graph()) == expected


class TestOrdersSnapshot:
    """5.3：订单列表序列化快照（对照契约 §7.6.4 订单列表示例）。"""

    def test_orders_snapshot_text(self):
        expected = "\n".join(
            [
                "PAGE: 订单列表  URL=https://orders.example.com/list",
                "",
                "REGION TABLE T1 订单列表",
                "  REGION ROWGROUP G1 表头区",
                "    REGION ROW R1 表头行",
                '      CELL [1] 订单号="订单号"',
                '      CELL [2] 客户="客户"',
                '      CELL [3] 金额="金额"',
                '      CELL [4] 状态="状态"',
                '      CELL [5] 操作="操作"',
                "  REGION ROWGROUP G2 表体区",
                "    REGION ROW R2 订单行1",
                '      CELL [6] 订单号="ORD-001"',
                '      CELL [7] 客户="甲公司"',
                '      CELL [8] 金额="¥98.00"',
                '      CELL [9] 状态="待审批"',
                '      ACTOR [10] button "批准" text="批准"',
                "    REGION ROW R3 订单行2",
                '      CELL [11] 订单号="ORD-002"',
                '      CELL [12] 客户="乙公司"',
                '      CELL [13] 金额="¥152.00"',
                '      CELL [14] 状态="待审批"',
                '      ACTOR [15] button "批准" text="批准"',
            ]
        )
        assert serialize(_orders_graph()) == expected


class TestSerializationRules:
    """5.1：序列化规则（§7.6.2/§7.6.3）。"""

    def test_region_header(self):
        text = serialize(_login_form_graph())
        assert "REGION FORM F1 登录区" in text

    def test_part_of_as_indentation(self):
        text = serialize(_orders_graph())
        assert "  REGION ROWGROUP G1 表头区" in text
        assert "    REGION ROW R1 表头行" in text
        assert "      CELL [1] 订单号=" in text

    def test_text_bearing_format(self):
        text = serialize(_orders_graph())
        assert 'CELL [8] 金额="¥98.00"' in text

    def test_related_to_annotation(self):
        text = serialize(_login_form_graph())
        assert '(related-to: "用户名" 0.9·左侧邻近)' in text

    def test_sibling_visual_order(self):
        text = serialize(_orders_graph())
        # 兄弟按视觉顺序：表头行 5 列从左到右
        assert text.index("[1] 订单号") < text.index("[5] 操作")

    def test_state_rendering(self):
        text = serialize(_login_form_graph())
        assert 'CHECK [6] "记住我" checked' in text
        assert 'FIELD [2] textbox "用户名输入框" value=""' in text

    def test_id_and_bounds_not_in_text(self):
        text = serialize(_login_form_graph())
        assert "E1" not in text
        assert "bounds" not in text
        assert "10, 20" not in text

    def test_confidence_ambiguous_only(self):
        graph = _login_form_graph()
        graph.elements[0].confidence = "ambiguous"
        text = serialize(graph)
        assert "(歧义)" in text


class TestSerializeStability:
    """序列化确定性：同图同文本。"""

    def test_deterministic(self):
        assert serialize(_login_form_graph()) == serialize(_login_form_graph())
