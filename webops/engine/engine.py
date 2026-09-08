"""引擎函数执行实现（M5 spec §5.2/§5.4/§5.5，契约 §5.8.1/§5.8.2/§5.10）。

``EngineFunctions`` 把 M1 浏览器能力、M4 语义图与 M3 变量机制收敛为 LLM
可调用的函数集：每个引擎函数一个方法、统一返回 ``OpResult``，普通失败以
工具结果回传 LLM、致命错误抛出 ``FatalBrowserError``。依赖以构造注入方式
提供（design D6），便于 mock 独立测试、函数可扩展。

- **页面操作绑定**（§5.10）：click/type/semantic_graph 等作用于当前页面
  变量（M3 ``SchemaSpace.current_page``）指向的页面；页面切换由变量指定，
  LLM 不做页面切换决策。
- **ref 解析**（§7.8 策略 B）：LLM 传来的 ``[N]`` 经 ``EngineRefMap``
  确定性解析为 CSS 选择器（``ElementRef.id``），拒绝无效/过期 ref。
- **错误语义**（design D4）：普通失败返回 ``OpResult(ok=False)`` 回传 LLM；
  致命错误（浏览器崩溃等）抛出 ``FatalBrowserError`` 终止流程。
"""

from __future__ import annotations

from collections.abc import Callable

from webops.browser import (
    BrowserDriver,
    DomProbe,
    ElementRef,
    ErrorCode,
    FatalBrowserError,
    OpResult,
)
from webops.browser import (
    PageRef as BrowserPageRef,
)
from webops.browser.http import http_request as _http_request
from webops.engine.probe import EngineProbe
from webops.engine.refmap import EngineRefMap, RefResolution
from webops.engine.tools import ENGINE_TOOLS
from webops.schema import PageRef as SchemaPageRef
from webops.schema import SchemaFrame, SchemaSpace
from webops.schema.errors import SchemaError, SchemaTypeError
from webops.schema.path import resolve_target
from webops.schema.types import infer_type
from webops.semantic_graph import (
    LlmFiller,
    SemanticGraphBudgetExceeded,
    serialize,
)
from webops.semantic_graph import (
    semantic_graph as _generate_graph,
)
from webops.semantic_graph.errors import LlmStageError, ProgramStageError


class EngineFunctions:
    """引擎函数执行实现（M5 spec §5.2）。

    :param browser: M1 浏览器驱动（页面操作/HTTP/探针底层）。
    :param filler: M4 ``LlmFiller``（语义图 LLM 填充阶段，semantic_graph 注入）。
    :param schema_space: M3 ``SchemaSpace``（变量读写/页面变量绑定/类型校验）。
    :param current_frame: 返回当前 schema 帧的可调用对象（M6/M7 提供，
      M5 单测注入固定帧）。
    :param probe: M1 ``DomProbe``（默认 ``EngineProbe``，记录最近快照供 ref 刷新）。
    :param graph_generator: M4 ``semantic_graph`` 生成入口（默认真实实现，
      测试可注入 mock）。
    :param budget_limit: 语义图 token 预算上限（None 不检测）。
    :param page_var: ``open`` 写入的页面引用变量名（当前帧内，默认 ``page``）。
    :param download_dir: ``download`` 的保存目录。
    :param wait_timeout_ms: ``wait`` 默认超时（毫秒）。
    """

    def __init__(
        self,
        browser: BrowserDriver,
        filler: LlmFiller,
        schema_space: SchemaSpace,
        current_frame: Callable[[], SchemaFrame | None],
        *,
        probe: DomProbe | None = None,
        graph_generator: Callable | None = None,
        budget_limit: int | None = None,
        page_var: str = "page",
        download_dir: str = ".",
        wait_timeout_ms: int = 30000,
    ) -> None:
        self._browser = browser
        self._filler = filler
        self._space = schema_space
        self._frame_provider = current_frame
        self._probe = probe or EngineProbe(browser)
        self._generate_graph = graph_generator or _generate_graph
        self._budget_limit = budget_limit
        self._page_var = page_var
        self._download_dir = download_dir
        self._wait_timeout_ms = wait_timeout_ms
        self._ref_map = EngineRefMap()

    @property
    def ref_map(self) -> EngineRefMap:
        """当前 ref 映射表（供上层/测试检查）。"""
        return self._ref_map

    # ------------------------------------------------------------ 分发入口

    def call(self, name: str, arguments: dict | None = None) -> OpResult:
        """按函数名分发到对应执行方法（M6 的调用入口，design D1）。

        注册表驱动：函数名不在 ``ENGINE_TOOLS`` 中返回失败；参数缺失/类型
        不符返回 ``ok=False``；执行中的意外异常包装为失败结果（agent 语义，
        不中断会话）。致命错误 ``FatalBrowserError`` 原样上抛。
        """
        if not isinstance(name, str) or not name:
            return OpResult(False, f"函数名非法: {name!r}", {"code": ErrorCode.INVALID_ARGUMENT})
        known = {tool.name for tool in ENGINE_TOOLS}
        if name not in known:
            return OpResult(False, f"未知引擎函数: {name}", {"code": ErrorCode.INVALID_ARGUMENT})
        method = getattr(self, name, None)
        if method is None or not callable(method):
            return OpResult(
                False,
                f"引擎函数 {name} 未实现",
                {"code": ErrorCode.UNKNOWN, "function": name},
            )
        if arguments is not None and not isinstance(arguments, dict):
            return OpResult(
                False,
                f"参数必须是对象: {arguments!r}",
                {"code": ErrorCode.INVALID_ARGUMENT, "function": name},
            )
        args = dict(arguments or {})
        return self._guard(lambda: self._invoke(method, args))

    @staticmethod
    def _invoke(method: Callable, args: dict) -> OpResult:
        try:
            return method(**args)
        except TypeError as exc:
            return OpResult(
                False,
                f"引擎函数参数错误: {exc}",
                {"code": ErrorCode.INVALID_ARGUMENT},
            )

    @staticmethod
    def _guard(fn: Callable[[], OpResult]) -> OpResult:
        """普通失败包装为 ``OpResult``；致命错误 ``FatalBrowserError`` 上抛。"""
        try:
            return fn()
        except FatalBrowserError:
            raise
        except Exception as exc:
            return OpResult(False, f"引擎函数执行失败: {exc}", {"code": ErrorCode.UNKNOWN})

    # ------------------------------------------------------------ 页面函数

    def open(self, url: str, save_to: str | None = None) -> OpResult:
        """打开页面，把新建页签的页面引用写入变量（契约 §5.10）。

        :param url: 要打开的 URL。
        :param save_to: 页面引用写入的目标变量（形如 ``this/页面A``）；
          省略时写入默认活动页变量 ``this/{page_var}``。
        """
        result = self._browser.open(url)
        if not result.ok:
            return result
        browser_ref = result.detail["page_ref"]
        page_url = result.detail.get("url", "")
        frame = self._frame_provider()
        if frame is None:
            return OpResult(
                False,
                "当前 schema 帧不可用，无法写入页面引用变量",
                {"code": ErrorCode.INVALID_ARGUMENT},
            )
        schema_ref = SchemaPageRef(page_id=browser_ref.id, url=page_url)
        if save_to:
            var_path = self._normalize_var_path(save_to)
        else:
            var_path = f"this/{self._page_var}"
        try:
            self._space.write(frame, var_path, schema_ref, "页面引用")
        except SchemaError as exc:
            return OpResult(
                False,
                f"页面引用写入变量失败: {exc}",
                {"code": ErrorCode.INVALID_ARGUMENT, "var": var_path},
            )
        return OpResult(
            True,
            detail={"page_ref": browser_ref, "var": var_path, "url": page_url},
        )

    def activate(self, page_var: str) -> OpResult:
        """把已打开的页面设为当前活动页（§5.10 多页签切换）。

        后续 click/type/semantic_graph 等操作作用于该页签。page_var 必须是
        已存储的页面引用变量（如 ``this/页面A``）。
        """
        frame = self._frame_provider()
        if frame is None:
            return OpResult(False, "当前 schema 帧不可用", {"code": ErrorCode.INVALID_REF})
        try:
            target, var = self._resolve_var(frame, page_var)
        except SchemaError as exc:
            return OpResult(
                False,
                f"activate 目标无效: {exc}",
                {"code": ErrorCode.INVALID_ARGUMENT},
            )
        page_ref = target.storage.get(var)
        if not isinstance(page_ref, SchemaPageRef):
            return OpResult(
                False,
                f"变量 {page_var!r} 不是页面引用（无法作为页签切换），请先用 open 打开并存入",
                {"code": ErrorCode.INVALID_ARGUMENT, "var": page_var},
            )
        # 校验页签仍打开（M1 取回 page 句柄）
        browser_result = self._browser.page(BrowserPageRef(id=page_ref.page_id))
        if not browser_result.ok:
            return OpResult(
                False,
                f"页签已关闭/不可用（{page_ref.page_id}），请重新 open",
                {"code": ErrorCode.INVALID_REF, "page_id": page_ref.page_id},
            )
        try:
            self._space.activate_page(target, var)
        except SchemaError as exc:
            return OpResult(False, f"activate 失败: {exc}", {"code": ErrorCode.INVALID_ARGUMENT})
        return OpResult(True, detail={"page_var": page_var, "page_id": page_ref.page_id})

    def get_url(self, save_to: str) -> OpResult:
        """取当前活动页的 URL 字符串并存入变量（类型 string/文本，与页签区分）。"""
        page_result = self._current_page_handle()
        if not page_result.ok:
            return page_result
        handle = page_result.detail["page"]
        frame = self._frame_provider()
        if frame is None:
            return OpResult(False, "当前 schema 帧不可用", {"code": ErrorCode.INVALID_REF})
        try:
            self._space.write(frame, self._normalize_var_path(save_to), handle.url, "文本")
        except SchemaError as exc:
            return OpResult(
                False, f"URL 写入变量失败: {exc}", {"code": ErrorCode.INVALID_ARGUMENT}
            )
        return OpResult(True, detail={"var": self._normalize_var_path(save_to), "url": handle.url})

    def semantic_graph(self, scope: str = "full", lod: int = 2) -> OpResult:
        """生成当前页面变量的语义图（委托 M4，无缓存，每次完整生成）。

        生成后刷新 ref 映射表并作废旧 ref（§7.8 策略 B）。
        """
        page_result = self._current_page_handle()
        if not page_result.ok:
            return page_result
        page_ref = page_result.detail["page"].page_ref
        try:
            graph = self._generate_graph(
                page_ref,
                scope=scope,
                lod=lod,
                probe=self._probe,
                filler=self._filler,
                budget_limit=self._budget_limit,
            )
        except ProgramStageError as exc:
            return OpResult(
                False,
                f"语义图生成失败（程序侧）: {exc}",
                {"code": ErrorCode.NOT_FOUND},
            )
        except LlmStageError as exc:
            return OpResult(
                False,
                f"语义图生成失败（LLM 填充）: {exc}",
                {"code": ErrorCode.UNKNOWN},
            )
        except SemanticGraphBudgetExceeded as exc:
            return OpResult(
                False,
                f"语义图生成失败（预算超限）: {exc}",
                {"code": ErrorCode.UNKNOWN},
            )
        snapshot = getattr(self._probe, "last_snapshot", None)
        self._ref_map.refresh(graph, snapshot)
        return OpResult(
            True,
            detail={
                "graph": graph,
                "text": serialize(graph),
                "ref_count": len(graph.elements),
            },
        )

    # ------------------------------------------------------------ 操作类函数

    def click(self, ref: str) -> OpResult:
        """点击语义图元素（作用于当前页面）。"""
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        return handle.click(ElementRef(resolution.selector))

    def type(self, ref: str, text: str) -> OpResult:
        """向输入元素输入文本（作用于当前页面）。"""
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        return handle.type(ElementRef(resolution.selector), text)

    def select(self, ref: str, option: str) -> OpResult:
        """下拉选择（作用于当前页面）。"""
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        return handle.select(ElementRef(resolution.selector), option)

    def check(self, ref: str) -> OpResult:
        """勾选勾选类控件（作用于当前页面）。"""
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        return handle.check(ElementRef(resolution.selector))

    def uncheck(self, ref: str) -> OpResult:
        """取消勾选勾选类控件（作用于当前页面）。"""
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        return handle.uncheck(ElementRef(resolution.selector))

    def scroll(self, direction: str) -> OpResult:
        """滚动当前页面（up/down/left/right/top/bottom）。"""
        page_result = self._current_page_handle()
        if not page_result.ok:
            return page_result
        return page_result.detail["page"].scroll(direction)

    def wait(self, condition: str) -> OpResult:
        """等待条件满足（作用于当前页面，默认超时）。"""
        page_result = self._current_page_handle()
        if not page_result.ok:
            return page_result
        return page_result.detail["page"].wait(condition, self._wait_timeout_ms)

    # ------------------------------------------------------------ 文件函数

    def download(self, ref: str) -> OpResult:
        """触发下载并保存（作用于当前页面）。"""
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        return handle.download(ElementRef(resolution.selector), self._download_dir)

    def upload(self, ref: str, path: str) -> OpResult:
        """上传文件到文件选择控件（作用于当前页面）。"""
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        return handle.upload(ElementRef(resolution.selector), path)

    # ------------------------------------------------------------ HTTP 函数

    def clear_requests(self) -> OpResult:
        """清理页面请求记录（形态 A）。"""
        self._browser.http_recorder.clear()
        return OpResult(True, detail={})

    def get_response(self, method: str, url_pattern: str) -> OpResult:
        """读取匹配的页面请求响应（形态 A，无匹配返回失败）。"""
        response = self._browser.http_recorder.get_response(method, url_pattern)
        if response is None:
            return OpResult(
                False,
                f"无匹配请求响应: {method} {url_pattern}",
                {"code": ErrorCode.NOT_FOUND, "method": method, "url_pattern": url_pattern},
            )
        return OpResult(True, detail={"response": response})

    def http_request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        body: str | None = None,
    ) -> OpResult:
        """发起独立 HTTP 请求（形态 B，不经页面，认证经 headers 显式提供）。"""
        return _http_request(method, url, headers=headers, body=body)

    # ------------------------------------------------------------ 提取函数

    def extract(self, ref: str, target: str) -> OpResult:
        """提取语义图元素值并写入 schema 变量（写入前经 M3 类型校验，§5.3）。"""
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        value = resolution.value if resolution.value else resolution.text
        frame = self._frame_provider()
        if frame is None:
            return OpResult(
                False,
                "当前 schema 帧不可用，无法写入变量",
                {"code": ErrorCode.INVALID_ARGUMENT},
            )
        type_name = self._declared_type(frame, target) or infer_type(value)
        try:
            self._space.write(frame, target, value, type_name)
        except SchemaTypeError as exc:
            return OpResult(
                False,
                f"提取值类型校验失败: {exc}",
                {"code": ErrorCode.INVALID_ARGUMENT, "var": target},
            )
        except SchemaError as exc:
            return OpResult(
                False,
                f"变量写入失败: {exc}",
                {"code": ErrorCode.INVALID_ARGUMENT, "var": target},
            )
        return OpResult(True, detail={"var": target, "value": value, "type": type_name})

    # ------------------------------------------------------------ 内部

    def _normalize_var_path(self, path: str) -> str:
        """变量路径归一化：``$this/x`` → ``this/x``；裸 ``x`` → ``this/x``。"""
        p = (path or "").strip()
        if p.startswith("$this/"):
            return "this/" + p[len("$this/") :]
        if p.startswith("this/"):
            return p
        return f"this/{p}"

    def _resolve_var(self, frame: SchemaFrame, path: str):
        """解析变量路径为 (目标帧, 帧内变量名)；越权/非法抛 SchemaError。"""
        from webops.schema.path import resolve_target

        return resolve_target(frame, self._normalize_var_path(path))

    def _current_page_handle(self) -> OpResult:
        """从当前页面变量解析出目标 page 句柄（M3 §5.10 → M1）。"""
        frame = self._frame_provider()
        if frame is None:
            return OpResult(False, "当前 schema 帧不可用", {"code": ErrorCode.INVALID_REF})
        page_ref = self._space.current_page(frame)
        if page_ref is None:
            return OpResult(
                False,
                "无当前页面变量（尚无打开的页面）",
                {"code": ErrorCode.INVALID_REF},
            )
        return self._browser.page(BrowserPageRef(id=page_ref.page_id))

    def _resolve_ref(self, ref: str, page_handle) -> OpResult:
        """解析 ref：无效/过期返回失败，合法返回解析结果（detail["resolution"]）。"""
        status, resolution = self._ref_map.resolve(ref, current_url=page_handle.url)
        if status == "stale":
            return OpResult(
                False,
                f"ref {ref} 已过期，请重新获取快照（semantic_graph）",
                {"code": ErrorCode.INVALID_REF, "ref": ref},
            )
        if status == "invalid":
            return OpResult(
                False,
                f"无效 ref: {ref}（不在当前 ref 映射表中）",
                {"code": ErrorCode.INVALID_REF, "ref": ref},
            )
        return OpResult(True, detail={"resolution": resolution})

    def _bind(self, ref: str) -> tuple[object, RefResolution | None, OpResult | None]:
        """绑定目标：当前页面句柄 + ref 解析结果；失败返回失败结果。"""
        page_result = self._current_page_handle()
        if not page_result.ok:
            return None, None, page_result
        page_handle = page_result.detail["page"]
        ref_result = self._resolve_ref(ref, page_handle)
        if not ref_result.ok:
            return None, None, ref_result
        return page_handle, ref_result.detail["resolution"], None

    @staticmethod
    def _declared_type(frame: SchemaFrame, path: str) -> str | None:
        """目标变量已声明的类型（帧声明/已写入声明），未声明返回 None。"""
        try:
            _, var = resolve_target(frame, path)
        except SchemaError:
            return None
        for source in (frame.outputs, frame.inputs, frame.declared):
            if var in source:
                return source[var]
        return None


__all__ = ["EngineFunctions"]
