"""浏览器插件（M7 插件集）：网页操作能力。

自包含浏览器驱动、语义图生成、元素引用映射与页面对象。函数只返回值
（业务值 + 报告附加信息），不写变量（引擎落笔）。

- 页面对象：``plugins.common.PageObject``（泛型 ``object`` 值）。
- 当前活动页：由插件维护（最近 open / activate 的页面）。
- ``semantic_graph`` 时强制截图并写入报告附加信息。
"""

from __future__ import annotations

import os
import time
from typing import Any

from autobranch.plugin_system import FunctionResult, PluginBase, engine_function
from autobranch.plugins.browser.driver import BrowserDriver, ElementRef
from autobranch.plugins.browser.driver.http import http_request as _http_request
from autobranch.plugins.browser.driver.models import PageRef as BrowserPageRef
from autobranch.plugins.browser.probe import EngineProbe
from autobranch.plugins.browser.refmap import EngineRefMap
from autobranch.plugins.browser.semantic_graph import (
    SemanticGraphBudgetExceeded,
    serialize,
)
from autobranch.plugins.browser.semantic_graph import (
    semantic_graph as _generate_graph,
)
from autobranch.plugins.browser.semantic_graph.errors import LlmStageError, ProgramStageError
from autobranch.plugins.common import PageObject

_PAGE_DESC = "页面对象（open 返回，可存入变量；activate 接收）"
_REF_DESC = "语义图元素引用（如 [1]，来自最近一次 semantic_graph）"


def _props(required: tuple[str, ...], **props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(required)}


class BrowserPlugin(PluginBase):
    """浏览器能力插件（懒装配：``init`` 时经 runtime 浏览器工厂创建驱动）。"""

    name = "browser"
    description = (
        "浏览器网页操作能力：打开/切换页面、点击/输入/选择、提取元素值、"
        "语义图（看页面）、滚动/等待、下载/上传、HTTP 请求与响应读取"
    )

    def __init__(self) -> None:
        self._browser: BrowserDriver | None = None
        self._probe: EngineProbe | None = None
        self._ref_map: EngineRefMap | None = None
        self._filler: Any = None
        self._current_page: PageObject | None = None
        self._runtime: Any = None

    # ------------------------------------------------------------ 生命周期

    def init(self, runtime: Any = None) -> None:
        self._runtime = runtime
        factory = getattr(runtime, "browser_factory", None) if runtime is not None else None
        self._browser = factory() if factory is not None else BrowserDriver()
        # 懒装配：首次用到浏览器时才冷启动驱动（纯计算行为树零浏览器开销）
        if self._browser is not None and callable(getattr(self._browser, "start", None)):
            from autobranch.plugins.browser.driver import BrowserConfig

            cfg = getattr(runtime, "browser_config", None)
            self._browser.start(cfg if isinstance(cfg, BrowserConfig) else BrowserConfig())
        self._probe = EngineProbe(self._browser)
        self._ref_map = EngineRefMap()
        self._filler = getattr(runtime, "llm_filler", None) if runtime is not None else None
        self._current_page = None

    def release(self) -> None:
        if self._browser is not None:
            try:
                self._browser.stop()
            except Exception:  # noqa: BLE001 - 释放失败不阻断
                pass
        self._browser = None
        self._ref_map = None

    @property
    def browser(self) -> BrowserDriver | None:
        return self._browser

    # ------------------------------------------------------------ 页面函数

    @engine_function(
        name="open",
        description=(
            "打开 URL 新建页签并设为当前活动页，返回页面对象（可存入变量供后续 "
            "activate 切换；描述含 [[set]] 声明时由引擎写入目标变量）"
        ),
        parameters=_props(("url",), url={"type": "string", "description": "要打开的 URL"}),
        output_param="save_to",
        returns=("page",),
    )
    def open(self, url: str) -> FunctionResult:
        browser = self._browser
        if browser is None:
            return FunctionResult.failure("浏览器未装配（browser 能力未加载）")
        result = browser.open(url)
        if not result.ok:
            return FunctionResult.failure(result.error or "打开页面失败", code="BROWSER_ERROR")
        ref = result.detail["page_ref"]
        page = PageObject(id=ref.id, url=result.detail.get("url", ""))
        self._current_page = page
        return FunctionResult.success(page, url=page.url, ok=True)

    @engine_function(
        name="activate",
        description="把已打开的页签设为当前活动页（切换焦点，不新建）；page 传页面对象变量",
        parameters=_props(("page",), page={"type": "string", "description": _PAGE_DESC}),
        returns=("page",),
    )
    def activate(self, page: PageObject) -> FunctionResult:
        browser = self._browser
        if browser is None:
            return FunctionResult.failure("浏览器未装配（browser 能力未加载）")
        if not isinstance(page, PageObject):
            return FunctionResult.failure(
                f"activate 参数 page 应为页面对象，收到 {type(page).__name__}"
            )
        result = browser.activate_page(BrowserPageRef(id=page.id))
        if not result.ok:
            return FunctionResult.failure(result.error or "页签切换失败", code="BROWSER_ERROR")
        self._current_page = page
        return FunctionResult.success(page)

    @engine_function(
        name="get_url",
        description="取当前活动页的 URL 字符串（产出型：经目标变量保存）",
        parameters=_props(()),
        output_param="save_to",
        returns=("url",),
    )
    def get_url(self) -> FunctionResult:
        handle = self._current_page_handle()
        if handle is None:
            return FunctionResult.failure("无当前页面（尚未打开任何页面）", code="INVALID_REF")
        return FunctionResult.success(handle.url)

    # ------------------------------------------------------------ 操作函数

    @engine_function(
        name="click",
        description="点击语义图元素（作用于当前页面）",
        parameters=_props(("ref",), ref={"type": "string", "description": _REF_DESC}),
    )
    def click(self, ref: str) -> FunctionResult:
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        result = handle.click(ElementRef(resolution.selector))
        return self._ok_result(result)

    @engine_function(
        name="type",
        description="向输入元素输入文本（替换现有值，作用于当前页面）",
        parameters=_props(
            ("ref", "text"),
            ref={"type": "string", "description": _REF_DESC},
            text={"type": "string", "description": "要输入的文本"},
        ),
    )
    def type(self, ref: str, text: str) -> FunctionResult:
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        return self._ok_result(handle.type(ElementRef(resolution.selector), text))

    @engine_function(
        name="select",
        description="下拉选择选项（优先按选项文本匹配，其次按 value 匹配）",
        parameters=_props(
            ("ref", "option"),
            ref={"type": "string", "description": _REF_DESC},
            option={"type": "string", "description": "要选择的选项文本或 value"},
        ),
    )
    def select(self, ref: str, option: str) -> FunctionResult:
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        return self._ok_result(handle.select(ElementRef(resolution.selector), option))

    @engine_function(
        name="check",
        description="勾选勾选类控件（checkbox/radio，作用于当前页面）",
        parameters=_props(("ref",), ref={"type": "string", "description": _REF_DESC}),
    )
    def check(self, ref: str) -> FunctionResult:
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        return self._ok_result(handle.check(ElementRef(resolution.selector)))

    @engine_function(
        name="uncheck",
        description="取消勾选勾选类控件（checkbox/radio，作用于当前页面）",
        parameters=_props(("ref",), ref={"type": "string", "description": _REF_DESC}),
    )
    def uncheck(self, ref: str) -> FunctionResult:
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        return self._ok_result(handle.uncheck(ElementRef(resolution.selector)))

    @engine_function(
        name="scroll",
        description="滚动当前页面（up/down/left/right/top/bottom）",
        parameters=_props(
            ("direction",),
            direction={
                "type": "string",
                "description": "滚动方向",
                "enum": ["up", "down", "left", "right", "top", "bottom"],
            },
        ),
    )
    def scroll(self, direction: str) -> FunctionResult:
        handle = self._current_page_handle()
        if handle is None:
            return FunctionResult.failure("无当前页面", code="INVALID_REF")
        return self._ok_result(handle.scroll(direction))

    @engine_function(
        name="wait",
        description="等待条件满足（selector: <CSS>/text: <文本>/url: <子串>，默认 selector）",
        parameters=_props(
            ("condition",),
            condition={"type": "string", "description": "等待条件，如 selector: #login-btn"},
        ),
    )
    def wait(self, condition: str) -> FunctionResult:
        handle = self._current_page_handle()
        if handle is None:
            return FunctionResult.failure("无当前页面", code="INVALID_REF")
        timeout = getattr(self._runtime, "wait_timeout_ms", 30000) if self._runtime else 30000
        return self._ok_result(handle.wait(condition, timeout))

    # ------------------------------------------------------------ 文件函数

    @engine_function(
        name="download",
        description="触发下载（点击下载链接/按钮）并保存文件",
        parameters=_props(("ref",), ref={"type": "string", "description": _REF_DESC}),
    )
    def download(self, ref: str) -> FunctionResult:
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        download_dir = getattr(self._runtime, "download_dir", ".") if self._runtime else "."
        return self._ok_result(handle.download(ElementRef(resolution.selector), download_dir))

    @engine_function(
        name="upload",
        description="上传文件到文件选择控件（作用于当前页面）",
        parameters=_props(
            ("ref", "path"),
            ref={"type": "string", "description": _REF_DESC},
            path={"type": "string", "description": "本地文件路径"},
        ),
    )
    def upload(self, ref: str, path: str) -> FunctionResult:
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        return self._ok_result(handle.upload(ElementRef(resolution.selector), path))

    # ------------------------------------------------------------ 语义图

    @engine_function(
        name="semantic_graph",
        description="获取当前页面的语义图（每次完整生成、无缓存，生成后旧 ref 失效；同时截图）",
        parameters=_props(
            ("scope", "lod"),
            scope={"type": "string", "description": "范围：full 全页，或区域 id（如 F1/T1）"},
            lod={
                "type": "integer",
                "minimum": 0,
                "maximum": 3,
                "description": "LOD 级别 0~3（信息量递增）",
            },
        ),
        returns=("graph",),
    )
    def semantic_graph(self, scope: str = "full", lod: int = 2) -> FunctionResult:
        page = self._current_page
        browser = self._browser
        if browser is None:
            return FunctionResult.failure("浏览器未装配（browser 能力未加载）")
        if page is None:
            return FunctionResult.failure("无当前页面（尚未打开任何页面）", code="INVALID_REF")
        try:
            graph = _generate_graph(
                BrowserPageRef(id=page.id),
                scope=scope,
                lod=lod,
                probe=self._probe,
                filler=self._filler,
                budget_limit=(
                    getattr(self._runtime, "budget_limit", None) if self._runtime else None
                ),
            )
        except ProgramStageError as exc:
            return FunctionResult.failure(f"语义图生成失败（程序侧）: {exc}", code="NOT_FOUND")
        except LlmStageError as exc:
            return FunctionResult.failure(f"语义图生成失败（LLM 填充）: {exc}")
        except SemanticGraphBudgetExceeded as exc:
            return FunctionResult.failure(f"语义图生成失败（预算超限）: {exc}")
        snapshot = getattr(self._probe, "last_snapshot", None)
        if self._ref_map is not None:
            self._ref_map.refresh(graph, snapshot)
        text = serialize(graph)
        screenshot = self._capture_screenshot()
        report = None
        if screenshot is not None:
            report = {"sections": [{"title": "截图", "body": screenshot}]}
        return FunctionResult.success(
            graph,
            text=text,
            ref_count=len(graph.elements),
            screenshot=screenshot or "",
            report=report,
        )

    # ------------------------------------------------------------ HTTP

    @engine_function(
        name="clear_requests",
        description="清理页面请求记录（此后只读取新发生的页面请求）",
        parameters=_props(()),
    )
    def clear_requests(self) -> FunctionResult:
        if self._browser is None:
            return FunctionResult.failure("浏览器未装配（browser 能力未加载）")
        self._browser.http_recorder.clear()
        return FunctionResult.success()

    @engine_function(
        name="get_response",
        description="读取页面已发生且与模式匹配的请求响应（无匹配返回失败）",
        parameters=_props(
            ("method", "url_pattern"),
            method={"type": "string", "description": "HTTP 方法，如 GET/POST"},
            url_pattern={"type": "string", "description": "URL 模式（* 为通配符）"},
        ),
    )
    def get_response(self, method: str, url_pattern: str) -> FunctionResult:
        if self._browser is None:
            return FunctionResult.failure("浏览器未装配（browser 能力未加载）")
        response = self._browser.http_recorder.get_response(method, url_pattern)
        if response is None:
            return FunctionResult.failure(
                f"无匹配请求响应: {method} {url_pattern}", code="NOT_FOUND"
            )
        return FunctionResult.success(response)

    @engine_function(
        name="http_request",
        description="发起独立 HTTP 请求（不经页面；认证经 headers 显式提供）",
        parameters=_props(
            ("method", "url"),
            method={"type": "string", "description": "HTTP 方法，如 GET/POST"},
            url={"type": "string", "description": "请求 URL"},
            headers={"type": "object", "description": "请求头"},
            body={"type": "string", "description": "请求体"},
        ),
    )
    def http_request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        body: str | None = None,
    ) -> FunctionResult:
        result = _http_request(method, url, headers=headers, body=body)
        return self._ok_result(result)

    # ------------------------------------------------------------ 提取

    @engine_function(
        name="extract",
        description="提取语义图元素的值并返回（产出型：经目标变量保存）",
        parameters=_props(("ref",), ref={"type": "string", "description": _REF_DESC}),
        output_param="target",
        returns=("value",),
    )
    def extract(self, ref: str) -> FunctionResult:
        handle, resolution, failure = self._bind(ref)
        if failure is not None:
            return failure
        value = resolution.value if resolution.value else resolution.text
        return FunctionResult.success(value, ref=ref)

    # ------------------------------------------------------------ 内部

    def _current_page_handle(self):
        if self._browser is None or self._current_page is None:
            return None
        result = self._browser.page(BrowserPageRef(id=self._current_page.id))
        return result.detail.get("page") if result.ok else None

    def _bind(self, ref: str):
        """绑定目标：当前页面句柄 + ref 解析结果；失败返回失败结果。"""
        handle = self._current_page_handle()
        if handle is None:
            return (
                None,
                None,
                FunctionResult.failure(
                    "无当前页面（请先 open 或 semantic_graph）", code="INVALID_REF"
                ),
            )
        if self._ref_map is None:
            return None, None, FunctionResult.failure("浏览器未装配")
        status, resolution = self._ref_map.resolve(ref, current_url=handle.url)
        if status == "stale":
            return (
                None,
                None,
                FunctionResult.failure(
                    f"ref {ref} 已过期，请重新获取快照（semantic_graph）",
                    code="INVALID_REF",
                    ref=ref,
                ),
            )
        if status == "invalid":
            return (
                None,
                None,
                FunctionResult.failure(
                    f"无效 ref: {ref}（不在当前 ref 映射表中）", code="INVALID_REF", ref=ref
                ),
            )
        return handle, resolution, None

    def _capture_screenshot(self) -> str | None:
        """语义图时截图到 runtime 报告目录；失败返回 None（不阻断）。"""
        if self._browser is None or self._current_page is None:
            return None
        runtime = self._runtime
        base = getattr(runtime, "screenshot_dir", None) if runtime is not None else None
        if not base:
            return None
        try:
            os.makedirs(base, exist_ok=True)
            path = os.path.join(
                base,
                f"{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 1000}.png",
            )
            result = self._browser.page(BrowserPageRef(id=self._current_page.id))
            if not result.ok:
                return None
            shot = result.detail["page"].screenshot(path)
            return path if shot.ok else None
        except Exception:  # noqa: BLE001 - 截图失败不阻断语义图
            return None

    def _ok_result(self, op: Any) -> FunctionResult:
        """把 M1 ``OpResult`` 转为 ``FunctionResult``（detail 透传 JSON 可序列化部分）。"""
        if op.ok:
            return FunctionResult.success(ok=True, detail=dict(op.detail or {}))
        code = (op.detail or {}).get("code") or "BROWSER_ERROR"
        return FunctionResult.failure(op.error or "操作失败", code=code)


plugin = BrowserPlugin()


__all__ = ["BrowserPlugin", "plugin"]
