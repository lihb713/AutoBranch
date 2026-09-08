# M5 · 引擎函数层 Spec

> 依据契约 `docs/contract.md` §5.1（引擎动作函数）、§5.8（引擎执行基础设施）、§5.8.1（引擎函数集）、§5.8.2（HTTP 接口）、§5.10（页面操作绑定）、§8.8（semantic_graph 接口）。
>
> **实现状态：已实现 ✅**（OpenSpec change `m5-engine-functions`，2026-08）。代码位于 `webops/engine/`，测试位于 `tests/engine/`（含 `tests/engine_helpers.py` 共享假浏览器/快照构造器与 `tests/engine/test_integration.py` 集成测试）。本文件已与实现同步；涉及契约语义的实现细节见「与契约的接口细节」一节，供统一更新 `docs/contract.md`。

## 1. 概述

将浏览器底层能力（M1）、语义图生成（M4）与 schema 变量（M3）封装为**暴露给 LLM 的函数集**（§5.8.1）。这些函数是 LLM 在叶子节点 agent 式执行时的调用接口（工具定义），同时处理"当前页面变量"的操作绑定。**依赖 M1 + M4 + M3。**

## 2. 功能范围

| 功能 | 说明 | 契约依据 |
|---|---|---|
| 页面函数 | `open(url, save_to?)` 开新页并存页签；`activate(page_var)` 切回已存页签；`get_url(save_to)` 取当前页 url 存文本 | §5.8.1/§5.9/§5.10 |
| 操作类函数 | click/type/select/check/uncheck/scroll/wait（Playwright 封装，作用于当前页面变量） | §5.8.1 |
| 文件函数 | download/upload | §5.8.1 |
| 语义图函数 | `semantic_graph(范围, LOD)` | §8.8 |
| HTTP 函数 | clear_requests/get_response（形态 A）、http_request（形态 B） | §5.8.2 |
| 提取函数 | `extract(ref, 目标)` → 写入 schema 变量 | §5.3/§5.8.1 |
| 页面操作绑定 | 函数作用于当前活动页（最近 activate 的页签；无则最近 open 的页） | §5.10 |
| 函数可扩展 | 函数集随需求增减 | §5.8.1 |

## 3. 数据依赖

### 3.1 输入
- **工具调用参数**：LLM 选择的函数名 + 参数（ref、文本、范围、LOD 等）
- **当前页面变量**（来自 M3）：函数绑定的页面
- **浏览器能力**（来自 M1）：各操作函数实现
- **语义图生成**（来自 M4）：semantic_graph 接口

### 3.2 输出
- **工具调用结果**（`OpResult`）：成功/失败 + 错误信息，回传给 LLM（agent 语义）
- **变量写入副作用**：open 写页面引用、extract 写提取值（经 M3）

## 4. 单元间依赖

- **依赖**：
  - M1（浏览器驱动）— 操作/文件/HTTP/截图/DOM 爬取实现
  - M4（语义图生成）— semantic_graph 函数
  - M3（schema 命名空间）— 变量读写、页面变量绑定
- **被依赖**：
  - M6（叶子 agent 执行）— LLM 通过 M5 的函数集执行操作
  - M7（编排器）— 间接

## 5. 接口契约

### 5.1 工具函数注册表

引擎函数以**工具 schema** 形式暴露给 LLM（供 M0 会话使用），同时提供执行实现：

```python
ENGINE_TOOLS: list[ToolSpec] = [
    open, activate, get_url, click, type, select, check, uncheck,
    scroll, wait, download, upload,
    semantic_graph, clear_requests, get_response, http_request,
    extract,
]
```

### 5.2 函数签名（执行实现）

```python
class EngineFunctions:
    def open(self, url: str, save_to: str | None = None) -> OpResult: ...
    def activate(self, page_var: str) -> OpResult: ...
    def get_url(self, save_to: str) -> OpResult: ...
    def click(self, ref: str) -> OpResult: ...
    def type(self, ref: str, text: str) -> OpResult: ...
    def select(self, ref: str, option: str) -> OpResult: ...
    def check(self, ref: str) -> OpResult: ...
    def uncheck(self, ref: str) -> OpResult: ...
    def scroll(self, direction: str) -> OpResult: ...
    def wait(self, condition: str) -> OpResult: ...
    def download(self, ref: str) -> OpResult: ...
    def upload(self, ref: str, path: str) -> OpResult: ...
    def semantic_graph(self, scope: str, lod: int) -> OpResult: ...
    def clear_requests(self) -> OpResult: ...
    def get_response(self, method: str, url_pattern: str) -> OpResult: ...
    def http_request(self, method: str, url: str, headers: dict, body: str) -> OpResult: ...
    def extract(self, ref: str, target: str) -> OpResult: ...
```

### 5.3 ref 解析

- LLM 传来的 `ref`（如 `[1]`）→ ref 映射表（§7.8）→ 引擎侧元素 id → DOM 节点，全确定性
- 页面状态变化后旧 ref 失效（§7.8 方案 B），调用时校验

### 5.4 页面操作绑定（§5.10）

- click/type/semantic_graph 等作用于**当前页面变量**指向的页
- 页面切换由变量指定，LLM 不做页面切换决策

### 5.5 错误语义

- 函数失败（如 click 失败）→ `OpResult(ok=False, error=...)` 作为工具结果回传 LLM，由 LLM 自行修正
- 致命错误（浏览器崩溃）→ 抛出 `FatalBrowserError` 终止流程

## 6. 验收标准（全部已实现并通过测试 ✅）

- [x] 全部引擎函数可被 LLM 以工具形式调用并执行
- [x] 各函数绑定"当前页面变量"正确
- [x] ref 解析确定性：ref → 元素 id → DOM 节点，拒绝无效/过期 ref
- [x] open 返回页面引用并写入变量
- [x] extract 提取值写入变量，类型经 M3 校验
- [x] HTTP 形态 A/B 均可调用
- [x] 函数失败以工具结果返回（ok=False + 错误），不抛异常中断 agent
- [x] 致命错误能中断流程
- [x] 函数集可扩展：新增函数即注册即用

## 7. 测试策略

- **mock 语义图/M3**：各函数独立测试（mock M4 的 semantic_graph、M3 的变量读写）
- **ref 映射测试**：合法/过期 ref 的处理
- **绑定测试**：多页面变量下函数作用页正确
- **错误语义测试**：函数失败返回 OpResult(ok=False)，致命错误抛异常
- **集成测试**（可选）：真实浏览器 + 真实语义图，验证函数闭环
- **独立性**：测试以 mock 为主，不依赖 M6/M7

## 8. 与契约的接口细节（待统一更新 contract.md）

1. **结果类型复用**：`OpResult`/`FatalBrowserError` 直接复用 M1 定义（非重复定义），`ToolSpec` 复用 M0 定义；M5 在 `webops/engine/models.py` 统一再导出并提供 `success`/`failure` 便捷构造器。引擎函数统一返回 M1 `OpResult`。
2. **`EngineFunctions` 构造注入**（design D6）：`browser`（M1）/`filler`（M4 `LlmFiller`）/`schema_space`（M3）/`current_frame`（当前 schema 帧提供者）+ 可选 `probe`（默认 `EngineProbe`）、`graph_generator`（默认真实 M4 `semantic_graph`，测试注入 mock）、`budget_limit`、`page_var`（默认 `page`）、`download_dir`（默认 `.`）、`wait_timeout_ms`（默认 30000）。M6/M7 调用时注入真实依赖。
3. **调用入口 `call(name, arguments)`**：M6 经 `EngineFunctions.call` 按函数名分发（注册表驱动），参数缺失/类型不符返回 `ok=False`（参数错误），未知函数名返回 `ok=False`；`ENGINE_TOOLS` 扩展即自动可分发。
4. **ref 映射**（§7.8 策略 B）：`EngineRefMap` 维护 `[N]` ↔ 元素 id ↔ DOM 快照节点 ↔ CSS 选择器；选择器推导优先级：`#<dom_id>`（DOM `id` 属性）→ `tag:has-text("文本")`（无 id 且有可见文本的元素，如导航链接/按钮，可靠定位）→ 快照树标签路径兜底（`body > form > input`，中间被过滤节点会致路径不精确，仅作最后手段）。`semantic_graph` 每次生成刷新映射表并作废旧 ref；页面 URL 与快照 URL 不一致（导航）同样使 ref 过期。拒绝语义区分：从未出现=无效（`invalid`）、曾在历史快照出现=过期（`stale`）。
5. **`open`/`activate`/`get_url` 页面机制**：`open(url, save_to=None)` 开新页签，`save_to` 提供时把页面引用（PageRef）写入该变量（如 `{{set:page:this/页面A}}` 声明存页签），省略时写默认活动页变量（`this/{page_var}`）；`activate(page_var)` 把已存页签设为当前活动页（只切焦点不新建，变量非页面引用或页签已关返回明确错误）；`get_url(save_to)` 取当前活动页 url 存为文本（与页签区分，`{{set:string:...}}`）。
6. **`extract` 类型来源**：目标变量声明类型按 `frame.outputs → frame.inputs → frame.declared` 查找，未声明则按提取值 `infer_type` 推断；写入前经 M3 `check_type` 强校验，类型不匹配不写入并返回 `ok=False`。
7. **`wait`/`download` 缺省参数**：契约签名 `wait(condition)`/`download(ref)` 无超时/保存目录参数，实现使用构造缺省（`wait_timeout_ms=30000`、`download_dir="."`），M6 可按需配置。
8. **HTTP 形态**：形态 A（`clear_requests`/`get_response`）委托 M1 `HttpRecorder`（会话级）；形态 B（`http_request`）委托 M1 `webops.browser.http.http_request`（独立请求，认证经 `headers` 显式提供、不携带页面会话）。
9. **错误语义**（§5.5 确认）：所有普通失败（M1 程序侧失败、ref 无效/过期、类型校验失败、无匹配请求、无当前页面、参数错误、意外异常）返回 `OpResult(ok=False, error=..., detail["code"]=分类错误码)`；`FatalBrowserError`（浏览器崩溃/context 关闭）原样上抛不包装。`call` 内对意外异常兜底包装为 `ok=False`（`UNKNOWN`），不中断 agent 会话。
10. **页面绑定错误码**：无当前页面变量/当前 schema 帧不可用时返回 `ok=False`，`detail["code"]=INVALID_REF`（页绑定缺失，可恢复，LLM 应先 `open`）。
11. **语义图失败分类**：`ProgramStageError`（程序侧，可重试）→ `ok=False`（NOT_FOUND）；`LlmStageError`（LLM 填充失败）→ `ok=False`（UNKNOWN）；`SemanticGraphBudgetExceeded` → `ok=False`（UNKNOWN）；`FatalBrowserError` 上抛。
12. **测试覆盖**：单元测试 43 个（模型/注册表/分发/扩展/ref 映射/页面绑定/open/semantic_graph/HTTP 两形态/extract/wait-scroll/错误语义/模块独立性）+ 集成测试 1 个（真实浏览器 + 真实语义图闭环 open→semantic_graph→type/click→extract），全部经 `webops` conda 环境 `pytest` 通过；`ruff check .` 无告警。