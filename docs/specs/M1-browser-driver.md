# M1 · 浏览器驱动 Spec

> 依据契约 `docs/contract.md` §5.8.1（引擎函数集）、§5.8.2（HTTP 接口）、§5.8.3（报告截图）、§5.9（浏览器会话生命周期）、§5.10（页面变量机制）、§8（DOM 爬取）。
>
> **实现状态：已实现 ✅**（OpenSpec change `m1-browser-driver`，2026-08）。代码位于 `webops/browser/`，测试位于 `tests/browser/`。本文件已与实现同步；若契约语义有偏差，见文末「与契约的接口偏差」。

## 1. 概述

基于 Playwright 封装浏览器底层能力，提供 context/page 管理、元素操作、文件操作、HTTP 监听、截图与页面引用绑定。是唯一接触真实浏览器的模块。**无依赖、独立开发与测试。**

## 2. 功能范围

| 功能 | 说明 | 契约依据 | 状态 |
|---|---|---|---|
| context 管理 | 每次 run 全新 context，无持久化，全流程共享 | §5.9 | ✅ `BrowserDriver.start/stop` |
| page 管理 | 创建/关闭页面、页面引用 ↔ page 绑定 | §5.10 | ✅ `open/page/PageHandle.close` |
| 页面操作函数 | open/click/type/select/check/uncheck/scroll/wait | §5.8.1 | ✅ |
| 文件函数 | download/upload | §5.8.1 | ✅ |
| HTTP 监听 | clear / get_response（形态 A） | §5.8.2 | ✅ `HttpRecorder` |
| 独立请求 | http_request（形态 B） | §5.8.2 | ✅ `http_request` |
| 截图 | 当前页面状态截图 | §5.8.3 | ✅ `PageHandle.screenshot` |
| DOM 原始爬取 | 供 M4 程序化阶段使用的 DOM 树/几何/可见性数据 | §8.3 | ✅ `DomProbe.crawl` |

**非目标（第一版，均未实现）**：
- 不处理 iframe 内元素（语义图只覆盖主文档）
- 不处理懒加载/虚拟滚动/动态渲染
- 不持久化 cookie 跨运行复用

## 3. 数据依赖

### 3.1 输入
- **配置**：`BrowserConfig`（浏览器类型 chromium/firefox/webkit、headless、全局 timeout_ms、screenshot_dir）
- **操作参数**：ref（`ElementRef`，M1 层 id 即 CSS 选择器）、文本、选项、URL 等

### 3.2 输出
- **操作结果**：统一 `OpResult(ok, error, detail)`，失败时 `detail["code"]` 为分类错误码
- **页面引用**：`PageRef`（`open` 成功时返回于 `detail["page_ref"]`）
- **页面句柄**：`PageHandle`（`page` 成功时返回于 `detail["page"]`）
- **截图文件**：PNG 路径（`screenshot` 成功时返回于 `detail["path"]`）
- **DOM 快照**：`DomSnapshot`（节点树 + role + 可见性 + bounds + 程序化值）

## 4. 单元间依赖

- **依赖**：无
- **被依赖**：
  - M4（语义图生成）— 获取 DOM/几何/可见性数据，元素操作后页面状态
  - M5（引擎函数层）— 引擎函数的具体执行实现
  - M8（报告机制）— 截图能力
  - M3（schema 命名空间）— 页面变量 ↔ page 绑定（通过 M5 间接）

## 5. 接口契约（已实现）

### 5.1 会话生命周期（`webops/browser/driver.py`）

```python
class BrowserDriver:
    def start(self, config: BrowserConfig | None = None) -> None: ...
    def stop(self) -> None: ...
    def open(self, url: str, timeout_ms: int | None = None) -> OpResult: ...
    def page(self, page_ref: PageRef) -> OpResult: ...
```

- `start`：每次创建全新 context（可重复调用，先释放旧会话）；`stop` 幂等，完整释放 context 与全部页面。
- `open`：成功时 `detail = {"page_ref": PageRef, "url": url}`；加载超时/不可达返回 `ok=False`（`LOAD_TIMEOUT`/`NETWORK`），不产出可用引用。
- `page`：成功时 `detail = {"page": PageHandle}`；引用无效/已释放返回 `ok=False`（`INVALID_REF`）。

### 5.2 页面操作（作用于指定 page）

```python
class PageHandle:
    def click(self, ref: ElementRef) -> OpResult: ...
    def type(self, ref: ElementRef, text: str) -> OpResult: ...   # 替换式输入（fill）
    def select(self, ref: ElementRef, option: str) -> OpResult: ...  # label 优先、value 兜底
    def check(self, ref: ElementRef) -> OpResult: ...
    def uncheck(self, ref: ElementRef) -> OpResult: ...
    def scroll(self, direction: str) -> OpResult: ...   # up/down/left/right/top/bottom
    def wait(self, condition: str, timeout_ms: int) -> OpResult: ...
    def screenshot(self, path: str) -> OpResult: ...    # 成功 detail["path"]
    def download(self, ref: ElementRef, save_dir: str) -> OpResult: ...
    def upload(self, ref: ElementRef, file_path: str) -> OpResult: ...
    def close(self) -> OpResult: ...                    # 关闭本页，引用失效
```

- `wait` 条件语法：`selector: <CSS>`（默认，等待元素可见）、`text: <文本>`（等待文本出现）、`url: <子串>`（等待 URL 包含子串）；未带前缀按 selector 处理。
- 所有操作显式绑定 `PageRef`（设计 D4），失败返回携带分类错误码的 `OpResult`（契约 §9.4），浏览器致命错误抛 `FatalBrowserError`。

### 5.3 HTTP 接口（`webops/browser/http.py`）

```python
class HttpRecorder:
    def clear(self) -> None: ...
    def get_response(self, method: str, url_pattern: str) -> HttpResponse | None: ...

def http_request(method, url, headers=None, body=None, timeout_ms=None) -> OpResult: ...
```

- 形态A：context 订阅 response 事件记录到会话级内存表；`get_response` 按 method（大小写不敏感精确）+ URL 模式匹配返回首个；无匹配返回 `None`（非错误）；`clear` 后旧记录不可读。
- URL 模式：不含 `*` 按子串匹配；含 `*` 按通配符正则搜索（`*` → `.*`，匹配 URL 任意位置）。
- 形态B：独立 `requests` 客户端，认证信息由调用方显式提供，不自动附加页面 cookie；传输层失败返回 `ok=False`（`NETWORK`），HTTP 状态码由 `detail["response"]` 读取。

### 5.4 DOM 爬取接口（供 M4，`webops/browser/dom.py`）

```python
class DomProbe:
    def crawl(self, page_ref: PageRef, lod: LODSpec | None = None) -> DomSnapshot: ...
```

`DomSnapshot` 提供：节点树（`root` + `elements` 扁平列表）、role、可见性、包围盒 `bounds`、输入值/checked/disabled/selected/options/文本等程序化值（§8.3 程序化阶段）。无效引用抛 `PageRefError`（程序侧），浏览器崩溃/context 关闭抛 `FatalBrowserError`。

筛选与边界（§8.4 ⑤ / §8.9）：剔除 `display:none`/`visibility:hidden`/`aria-hidden`/零尺寸元素；只覆盖主文档不合并 iframe；LOD 深度维度控制语义容器嵌套层数（`-1` 不限，默认 LOD-3 全量）。

### 5.5 数据契约（`webops/browser/models.py`）

```python
@dataclass
class OpResult:
    ok: bool
    error: str | None = None          # 失败原因（供 LLM 工具结果回读）
    detail: dict | None = None        # 附加信息；失败时 detail["code"] = 分类错误码

@dataclass(frozen=True)
class ElementRef:
    id: str                           # M1 层解释为 CSS 选择器（确定性解析）

@dataclass(frozen=True)
class PageRef:
    id: str                           # 会话内自增（驱动级单调递增），stop 后失效

@dataclass(frozen=True)
class HttpResponse:
    method: str; url: str; status: int; headers: dict; body: str

@dataclass(frozen=True)
class LODSpec:
    depth: int; breadth: str; attributes: str; relations: str   # §9.5 四维；from_level(0~3)

@dataclass(frozen=True)
class Bounds:
    x: float; y: float; w: float; h: float                      # 视口坐标

@dataclass
class ElementNode:
    id: str; tag: str; role: str; dom_id: str
    text: str; value: str; checked: bool | None; disabled: bool
    selected: str; options: list[str]; visible: bool; bounds: Bounds | None
    depth: int; children: list["ElementNode"]

@dataclass
class DomSnapshot:
    url: str; title: str; lod: LODSpec; root: ElementNode | None; elements: list[ElementNode]
```

分类错误码常量见 `webops.browser.models.ErrorCode`：`SESSION_NOT_RUNNING` / `INVALID_REF` / `NOT_FOUND` / `NOT_VISIBLE` / `NOT_ENABLED` / `NOT_EDITABLE` / `NOT_INTERACTABLE` / `AMBIGUOUS` / `TIMEOUT` / `LOAD_TIMEOUT` / `NETWORK` / `DOWNLOAD_FAILED` / `UPLOAD_FAILED` / `INVALID_ARGUMENT` / `UNKNOWN`。

### 5.6 错误语义（§9.4 程序侧失败）

- 元素不存在/隐藏/禁用/被遮挡/等待超时 → 返回 `ok=False` + `detail["code"]` 分类错误码 + `error` 信息，页面状态不变。
- 致命错误（浏览器崩溃、网络断开、context 关闭、会话已停止后操作）→ 抛出 `FatalBrowserError`，不吞没、终止流程（`webops/browser/errors.py`）。
- 独立请求的网络失败属程序侧可重试（`NETWORK`），不抛致命异常。

## 6. 验收标准（全部已实现并通过测试 ✅）

- [x] 每次 start 创建全新 context，无历史 cookie/登录态，stop 完整释放
- [x] open/click/type/select/check/uncheck/scroll/wait 在真实浏览器可执行
- [x] download/upload 可用
- [x] 页面请求监听：clear 后记录新请求，get_response 可按 method+url 模式匹配
- [x] http_request 可发起独立请求
- [x] 截图可保存并返回路径
- [x] 页面引用绑定正确：多页并存时操作作用于指定页
- [x] 致命错误可被识别并中断流程

## 7. 测试策略（`tests/browser/`，均打 `pytest.mark.integration` 标记）

- **真实浏览器测试**：本地 HTTP 测试服务器 fixture（`tests/browser/conftest.py`，端口随机）提供静态页面 `tests/fixtures/*.html` 与模拟 `/api/*`（回显）、`/files/data.txt`（下载）端点。
- **测试文件与覆盖**：
  - `test_contracts.py`（单元）：OpResult/ElementRef/PageRef/LODSpec/异常层级、URL 模式匹配、记录器 clear/get_response 纯逻辑
  - `test_session.py`：start/stop 生命周期、冷启动（cookie/localStorage 不残留）、同 context 共享 cookie
  - `test_pages.py`：多页并存、无效/已释放引用、多标签操作互不串页
  - `test_operations.py`：click/type/select/check/uncheck/scroll/wait + 失败分类（NOT_FOUND/NOT_VISIBLE/NOT_ENABLED/NOT_INTERACTABLE）
  - `test_files.py`：download 落盘内容正确、upload 控件收到文件
  - `test_http.py`：形态A 监听与清理、形态B 独立请求（认证头显式、无页面 cookie）
  - `test_screenshot.py`：PNG 有效、尺寸与视口一致、screenshot_dir 拼接
  - `test_dom.py`：快照结构/role/程序化值/bounds、隐藏与 aria-hidden 与 iframe 剔除、LOD 深度
  - `test_errors.py`：分类映射单元测试、操作统一返回、致命错误（浏览器崩溃/stop 后操作）
  - `test_independence.py`：模块不 import `webops.llm`、独立解释器可加载
- **独立性**：不依赖 LLM、不依赖行为树，`pytest tests/browser` 可单独运行。

## 8. 与契约的接口偏差（待统一处理 contract.md）

1. **`open` / `page` / `screenshot` 返回 `OpResult` 而非裸 `PageRef` / `PageHandle` / `str`**：依据 design.md D9「OpResult 作为所有操作的统一返回」，失败场景（open 不可达、引用无效、截图路径非法）才能返回可分类失败结果。产物经 `detail` 暴露：`open → detail["page_ref"]`、`page → detail["page"]`、`screenshot → detail["path"]`。
2. **分类错误码存放于 `OpResult.detail["code"]`**：`OpResult` 保持契约三字段 `ok/error/detail` 不变，错误码作为 `detail` 的扩展位（D9「detail 预留扩展位」）。
3. **`DomProbe.crawl` 无效引用抛 `PageRefError`**（程序侧可捕获），而非返回失败结果——爬取是返回数据的查询，`OpResult` 形态由 M4 调用侧决定。
4. **`HttpRecorder` 增加事件泵取**：Playwright sync API 的 asyncio 事件循环只在主线程的 API 调用期间运行，`get_response`/`clear` 前需短暂 `wait_for_timeout` 泵取 pending response 事件（约 50ms），否则刚发生的页面请求可能读不到。
5. **`PageRef.id` 驱动级单调递增**（跨会话不重置）：比「每会话自增」更安全，重启后旧引用不会误绑定到新会话的同编号页面。
6. **`ElementRef.id` 在 M1 层解释为 CSS 选择器**：M4/M5 的「语义图节点 id → CSS 选择器」映射在上层完成，M1 只做确定性解析（design.md Non-Goals）。