# engine-functions Specification

## Purpose

为 WebOps 的 LLM 叶子节点 agent 式执行提供统一引擎函数集：以工具 schema 暴露、可确定性解析 ref、绑定当前页面变量、写入 schema 变量并回传可分类结果，供 M6 叶子 agent 调用，依赖 M1 浏览器、M4 语义图与 M3 变量机制。

## Requirements

### Requirement: 工具函数注册表

系统 SHALL 以工具 schema 形式暴露一组引擎函数给 LLM（供 M0 会话使用），同时提供对应执行实现。注册表 SHALL 包含以下 15 个函数：`open`、`click`、`type`、`select`、`check`、`uncheck`、`scroll`、`wait`、`download`、`upload`、`semantic_graph`、`clear_requests`、`get_response`、`http_request`、`extract`。注册表 SHALL 是可扩展的：新增函数即可被 LLM 以工具形式调用并执行，无需改动既有函数。

#### Scenario: 注册表包含全部契约函数

- **WHEN** 上层（M6）读取引擎函数注册表
- **THEN** 注册表包含 open/click/type/select/check/uncheck/scroll/wait/download/upload/semantic_graph/clear_requests/get_response/http_request/extract 共 15 个函数，且每个函数均带可被 LLM 解析的工具 schema（函数名、参数与描述）

#### Scenario: 新增函数即注册即用

- **WHEN** 向注册表追加一个符合契约签名的新函数（如复合操作）
- **THEN** 该函数立即出现在暴露给 LLM 的工具列表中，且可通过注册表约定的调用入口被执行，无需修改既有函数

### Requirement: 函数执行实现与签名

系统 SHALL 提供 `EngineFunctions` 执行实现，每个引擎函数对应一个方法，其参数签名 SHALL 与契约一致：`open(url)`、`click(ref)`、`type(ref, text)`、`select(ref, option)`、`check(ref)`、`uncheck(ref)`、`scroll(direction)`、`wait(condition)`、`download(ref)`、`upload(ref, path)`、`semantic_graph(scope, lod)`、`clear_requests()`、`get_response(method, url_pattern)`、`http_request(method, url, headers, body)`、`extract(ref, target)`。每个函数 SHALL 返回统一的结果类型 `OpResult`，其中 SHALL 至少包含执行是否成功（ok）与失败时的错误信息（error）。

#### Scenario: 每个函数返回 OpResult

- **WHEN** 调用任一引擎函数并执行成功或失败
- **THEN** 该函数返回一个 `OpResult`，成功时 ok 为真且不含错误信息，失败时 ok 为假且 error 字段给出可读错误信息

#### Scenario: 参数缺失或类型不符时函数失败

- **WHEN** 调用函数时缺少必需参数或参数类型与签名不符
- **THEN** 该函数返回 ok 为假的 `OpResult` 并附参数错误信息，且不抛出异常中断调用方

### Requirement: ref 确定性解析

系统 SHALL 将 LLM 传来的 ref（如 `[1]`）按 ref 映射表解析为引擎侧元素 id，再定位到对应的 DOM 节点；该映射过程 SHALL 完全确定性、不依赖 LLM 提供 DOM 信息。系统 SHALL 拒绝无效 ref（不存在于映射表）与过期 ref（页面状态已变化导致失效），并以 ok 为假的 `OpResult` 回传拒绝原因。

#### Scenario: 合法 ref 解析到对应元素

- **WHEN** LLM 传入一个存在于当前 ref 映射表中的合法 ref
- **THEN** 系统将该 ref 确定性地映射到引擎侧元素 id 并定位到对应 DOM 节点，供操作函数使用

#### Scenario: 无效 ref 被拒绝

- **WHEN** LLM 传入一个不在 ref 映射表中的 ref（如凭空构造的编号）
- **THEN** 系统拒绝该 ref，返回 ok 为假的 `OpResult` 并附"无效 ref"错误信息，不执行任何页面操作

#### Scenario: 页面状态变化后过期 ref 被拒绝

- **WHEN** 页面状态发生变化（如导航、DOM 更新）导致旧 ref 映射失效，LLM 仍使用该过期 ref 调用操作函数
- **THEN** 系统拒绝该 ref，返回 ok 为假的 `OpResult` 并附"ref 已过期、请重新获取快照"错误信息，不执行任何页面操作

### Requirement: 页面操作绑定

系统 SHALL 将所有页面操作函数（`click`/`type`/`select`/`check`/`uncheck`/`scroll`/`wait`/`download`/`upload`/`semantic_graph`）绑定到**当前页面变量**所指向的页面执行；页面切换由变量指定，LLM 不做页面切换决策。当存在多个页面变量时，各函数的操作目标 SHALL 由当前页面变量决定。

#### Scenario: 操作函数作用于当前页面变量指向的页

- **WHEN** 当前页面变量指向页面 P1，LLM 调用 click/type/semantic_graph 等操作函数
- **THEN** 这些函数在页面 P1 上执行，且不作用于其他页面变量指向的页面

#### Scenario: 切换当前页面变量后操作目标随之改变

- **WHEN** 当前页面变量被切换为指向页面 P2 后，LLM 调用操作函数
- **THEN** 这些函数在页面 P2 上执行，而不再作用于 P1

#### Scenario: 无当前页面变量时操作函数失败

- **WHEN** 未设置当前页面变量（尚无打开的页面）而 LLM 调用页面操作函数
- **THEN** 系统返回 ok 为假的 `OpResult`，错误信息表明没有可绑定的当前页面

### Requirement: 变量写入副作用

系统 SHALL 支持两类变量写入副作用，且均经由 M3 变量机制完成：

- `open(url)` 打开页面后 SHALL 返回页面引用，并将该页面引用作为页面引用类型的变量写入 schema（契约 §5.10）
- `extract(ref, target)` 将目标元素提取出的值写入指定 schema 变量，写入前 SHALL 经 M3 类型校验，类型不匹配时写入失败并回传错误

#### Scenario: open 写入页面引用变量

- **WHEN** LLM 调用 `open(url)` 成功打开一个页面
- **THEN** 系统返回包含页面引用的 `OpResult`，且该页面引用已写入当前 schema 的页面引用类型变量，后续可经变量机制绑定为当前页面

#### Scenario: extract 写入变量并类型校验通过

- **WHEN** LLM 调用 `extract(ref, target)` 且目标 schema 变量声明的类型与提取值匹配
- **THEN** 提取值写入该变量，`OpResult` 为成功且附写入的变量路径与值

#### Scenario: extract 类型校验失败时不写入

- **WHEN** LLM 调用 `extract(ref, target)` 但提取值与目标 schema 变量声明的类型不匹配
- **THEN** 系统不写入该变量，返回 ok 为假的 `OpResult` 并附类型不匹配的错误信息

### Requirement: 错误语义

系统 SHALL 对引擎函数失败采用两级错误语义：普通函数失败（如 click 失败、ref 无效、类型校验失败）SHALL 以 `OpResult(ok=False, error=...)` 作为工具结果回传 LLM，由 LLM 自行修正，**不得抛出异常中断 agent 会话**；致命错误（如浏览器崩溃、浏览器进程不可用）SHALL 抛出 `FatalBrowserError` 异常，终止当前流程。

#### Scenario: 普通函数失败以工具结果回传

- **WHEN** 某操作函数执行失败（例如点击目标元素失败）
- **THEN** 函数返回 `OpResult(ok=False)` 及错误信息作为工具结果回传给 LLM，调用方不抛出异常，agent 会话得以继续

#### Scenario: 致命错误抛出 FatalBrowserError

- **WHEN** 执行函数时发生致命错误（例如浏览器崩溃、页面上下文不可用）
- **THEN** 系统抛出 `FatalBrowserError` 异常，当前流程终止

### Requirement: HTTP 两种形态

系统 SHALL 支持 HTTP 接口的两种形态（契约 §5.8.2）：形态 A 为页面上下文请求——`clear_requests()` 清理当前页面的请求记录、`get_response(method, url_pattern)` 读取页面已发生且与模式匹配的请求响应；形态 B 为独立请求——`http_request(method, url, headers, body)` 发起不经页面的独立 HTTP 请求，认证信息由流程文档的变量机制显式提供，不从页面会话自动提取。

#### Scenario: 形态 A 清理并读取页面请求

- **WHEN** LLM 依次调用 `clear_requests()`、触发页面请求（如 click）、再调用 `get_response(method, url_pattern)` 且请求匹配该模式
- **THEN** 系统先清理既有请求记录，随后返回触发请求中与 url_pattern 匹配、method 相符的响应内容

#### Scenario: 形态 A 无匹配请求时失败

- **WHEN** LLM 调用 `get_response(method, url_pattern)` 但页面记录中无与该模式匹配的请求
- **THEN** 系统返回 ok 为假的 `OpResult`，错误信息表明没有匹配的请求响应

#### Scenario: 形态 B 独立请求成功

- **WHEN** LLM 调用 `http_request(method, url, headers, body)` 发起独立请求
- **THEN** 系统发出该请求并返回响应结果，该请求不经过当前页面、不使用页面会话的 cookie

#### Scenario: 形态 B 认证信息显式提供

- **WHEN** LLM 调用 `http_request` 且认证所需 token/cookie 通过 headers 参数显式传入
- **THEN** 系统按传入的认证信息发起请求，且不从页面会话自动提取认证状态

### Requirement: semantic_graph 函数

系统 SHALL 提供 `semantic_graph(scope, lod)` 函数，SHALL 委托 M4 语义图生成，作用于当前页面变量指向的页面；每次调用 SHALL 完整生成、无缓存，返回语义图结果。范围与 LOD 参数 SHALL 控制语义图的覆盖区域与信息量。

#### Scenario: 获取当前页面语义图

- **WHEN** LLM 调用 `semantic_graph(scope, lod)` 且存在当前页面变量
- **THEN** 系统在该页面完整生成语义图（无缓存）并返回结果，结果包含的 ref 可被后续操作函数解析使用

#### Scenario: 语义图生成失败回传错误

- **WHEN** `semantic_graph` 委托的语义图生成失败（如 DOM 爬取异常）
- **THEN** 系统返回 ok 为假的 `OpResult` 并附生成失败的错误信息，不抛出异常中断 agent