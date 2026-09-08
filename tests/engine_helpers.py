"""M5 引擎函数层测试共享辅助（假浏览器/假探针/语义图与快照构造器）。

与 ``tests/fake_transport.py`` 同模式：位于 tests 根目录，经
``pythonpath=["tests"]`` 以顶层模块导入，供 ``tests/engine/`` 用例复用。
"""

from __future__ import annotations

from webops.browser import (
    DomSnapshot,
    ElementNode,
    ErrorCode,
    LODSpec,
    OpResult,
    PageRef,
)
from webops.semantic_graph import Element, ElementState, PageInfo, SemanticGraph


class FakePageHandle:
    """假页面句柄：记录操作调用，成功返回 OpResult（可配置失败/致命异常）。"""

    def __init__(self, page_ref: PageRef, url: str = "http://example.com/page"):
        self.page_ref = page_ref
        self.url = url
        self.calls: list[tuple] = []
        self.fail_with: Exception | None = None
        self.fail_result: OpResult | None = None

    def _result(self, *call_args) -> OpResult:
        if self.fail_with is not None:
            raise self.fail_with
        if self.fail_result is not None:
            return self.fail_result
        self.calls.append(call_args)
        return OpResult(True, detail={"page_ref": self.page_ref})

    def click(self, ref) -> OpResult:
        return self._result("click", ref.id)

    def type(self, ref, text) -> OpResult:
        return self._result("type", ref.id, text)

    def select(self, ref, option) -> OpResult:
        return self._result("select", ref.id, option)

    def check(self, ref) -> OpResult:
        return self._result("check", ref.id)

    def uncheck(self, ref) -> OpResult:
        return self._result("uncheck", ref.id)

    def scroll(self, direction) -> OpResult:
        return self._result("scroll", direction)

    def wait(self, condition, timeout_ms) -> OpResult:
        return self._result("wait", condition, timeout_ms)

    def download(self, ref, save_dir) -> OpResult:
        self.calls.append(("download", ref.id, save_dir))
        return OpResult(True, detail={"path": f"{save_dir}/x.zip", "page_ref": self.page_ref})

    def upload(self, ref, file_path) -> OpResult:
        return self._result("upload", ref.id, file_path)


class FakeBrowser:
    """假浏览器驱动：open/page 可控，内置 HttpRecorder 与页面句柄表。"""

    def __init__(self) -> None:
        from webops.browser import HttpRecorder

        self.pages: dict[str, FakePageHandle] = {}
        self.http_recorder = HttpRecorder()
        self.fail_open: bool = False

    def open(self, url: str) -> OpResult:
        if self.fail_open:
            return OpResult(False, "打开页面失败: mock", {"code": ErrorCode.NETWORK, "url": url})
        page_id = str(len(self.pages) + 1)
        handle = FakePageHandle(PageRef(page_id), url=url)
        self.pages[page_id] = handle
        return OpResult(True, detail={"page_ref": PageRef(page_id), "url": url})

    def page(self, page_ref: PageRef) -> OpResult:
        handle = self.pages.get(page_ref.id)
        if handle is None:
            return OpResult(
                False,
                f"无效页面引用: {page_ref.id}",
                {"code": ErrorCode.INVALID_REF},
            )
        return OpResult(True, detail={"page": handle})


class FakeProbe:
    """假 DOM 探针：携带最近一次爬取快照（供 ref 映射刷新）。"""

    def __init__(self, snapshot=None):
        self.last_snapshot = snapshot


def fake_response(method: str, url: str, status: int = 200, body: str = "{}"):
    """构造可被 HttpRecorder.record_response 消费的假 Playwright response。"""

    class _Req:
        def __init__(self):
            self.method = method

    class _Resp:
        def __init__(self):
            self.request = _Req()
            self.url = url
            self.status = status
            self.headers = {"content-type": "application/json"}

        def body(self) -> bytes:
            return body.encode("utf-8")

    return _Resp()


def make_snapshot(
    url: str = "http://example.com/page",
    dom_id: str = "username",
    tag: str = "input",
    value: str = "",
    text: str = "",
    node_id: str = "1",
) -> DomSnapshot:
    """构造单节点 DOM 快照（含 dom_id，ref 映射将得到 ``#<dom_id>`` 选择器）。"""
    node = ElementNode(
        id=node_id,
        tag=tag,
        role="textbox",
        dom_id=dom_id,
        value=value,
        text=text,
        depth=0,
    )
    root = ElementNode(id="root", tag="root", role="document", children=[node])
    return DomSnapshot(
        url=url,
        title="测试页",
        lod=LODSpec.from_level(2),
        root=root,
        elements=[node],
    )


def make_graph(
    url: str = "http://example.com/page",
    ref: str = "[1]",
    element_id: str = "E1",
    dom_node_id: str = "1",
    role: str = "textbox",
    tag: str = "input",
    value: str = "",
    text: str = "",
) -> SemanticGraph:
    """构造单元素语义图（与 ``make_snapshot`` 配对使用）。"""
    element = Element(
        id=element_id,
        ref=ref,
        role=role,
        purpose="测试元素",
        tag=tag,
        dom_node_id=dom_node_id,
        state=ElementState(value=value, text=text),
    )
    return SemanticGraph(
        page=PageInfo(url=url, title="测试页"),
        elements=[element],
    )


def fake_graph_generator(graph: SemanticGraph, snapshot: DomSnapshot):
    """构造 M4 ``semantic_graph`` 的假生成器：记录探针快照并返回固定图。"""

    def _generate(
        page_ref,
        scope: str = "full",
        lod: int = 2,
        probe=None,
        filler=None,
        budget_limit=None,
    ):
        if probe is not None:
            probe.last_snapshot = snapshot
        return graph

    return _generate


def build_engine(
    browser,
    *,
    space=None,
    frame=None,
    probe=None,
    graph_generator=None,
    filler=None,
    **kwargs,
):
    """构造 ``EngineFunctions`` 实例（默认注入假探针/假生成器/MockFiller）。"""
    from webops.engine import EngineFunctions
    from webops.schema import SchemaSpace
    from webops.semantic_graph import MockFiller

    if space is None:
        space = SchemaSpace()
    if frame is None:
        frame = space.enter_block("测试")
    if probe is None:
        probe = FakeProbe()
    if filler is None:
        filler = MockFiller()
    return EngineFunctions(
        browser=browser,
        filler=filler,
        schema_space=space,
        current_frame=lambda: frame,
        probe=probe,
        graph_generator=graph_generator,
        **kwargs,
    ), space, frame
