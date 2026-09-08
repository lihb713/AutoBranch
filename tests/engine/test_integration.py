"""M5 任务 6.3：集成测试（真实浏览器 + 真实语义图，``pytest -m integration``）。

跑通「open → semantic_graph → type → click → semantic_graph → extract」闭环：
从真实页面（tests/fixtures/sg_login.html）经 M1 浏览器 + M4 语义图流水线
（MockFiller 填充）+ M5 引擎函数执行，验证 ref 解析、页面绑定与变量写入
在真实链路下正确。
"""

from __future__ import annotations

import pytest

from webops.engine import EngineFunctions
from webops.schema import SchemaSpace
from webops.semantic_graph import MockFiller

pytestmark = pytest.mark.integration


class TestEngineIntegrationLogin:
    """登录页闭环：open → semantic_graph → type/click → extract。"""

    def _username_ref(self, graph):
        """视觉最上方的 textbox 即用户名输入框（密码框在下方）。"""
        textboxes = [element for element in graph.elements if element.role == "textbox"]
        assert textboxes
        username = min(textboxes, key=lambda element: (element.bounds.y, element.bounds.x))
        return username.ref

    def _remember_ref(self, graph):
        checkboxes = [element for element in graph.elements if element.role == "checkbox"]
        assert checkboxes
        return checkboxes[0].ref

    def test_open_type_click_extract_loop(self, eng_driver, eng_http_server):
        space = SchemaSpace()
        frame = space.enter_block("测试")
        engine = EngineFunctions(
            browser=eng_driver,
            filler=MockFiller(),
            schema_space=space,
            current_frame=lambda: frame,
        )

        result = engine.call("open", {"url": f"{eng_http_server}/sg_login.html"})
        assert result.ok, result.error
        assert space.current_page(frame) is not None

        sg = engine.call("semantic_graph", {"scope": "full", "lod": 2})
        assert sg.ok, sg.error
        graph1 = sg.detail["graph"]

        username_ref = self._username_ref(graph1)
        remember_ref = self._remember_ref(graph1)

        typed = engine.call("type", {"ref": username_ref, "text": "admin"})
        assert typed.ok, typed.error

        clicked = engine.call("click", {"ref": remember_ref})
        assert clicked.ok, clicked.error

        sg2 = engine.call("semantic_graph", {"scope": "full", "lod": 2})
        assert sg2.ok, sg2.error
        graph2 = sg2.detail["graph"]

        # 无缓存：第二次语义图反映最新输入值与勾选状态（§9.5）
        username2 = min(
            (e for e in graph2.elements if e.role == "textbox"),
            key=lambda e: (e.bounds.y, e.bounds.x),
        )
        assert username2.state.value == "admin"
        remember2 = next(e for e in graph2.elements if e.role == "checkbox")
        assert remember2.state.checked is True

        # 新 ref 下 extract 写入变量
        extracted = engine.call(
            "extract", {"ref": username2.ref, "target": "$this/用户名"}
        )
        assert extracted.ok, extracted.error
        assert space.read(frame, "$this/用户名") == "admin"
