## Why

WebOps 的 LLM 在叶子节点 agent 式执行时需要一套"能真正操作浏览器"的接口，但当前 M1 浏览器能力、M4 语义图与 M3 变量机制尚未收敛为暴露给 LLM 的统一函数集。依据 `docs/contract.md` §5.8（引擎执行基础设施）、§5.8.1（引擎函数集）、§5.8.2（HTTP 接口）、§5.10（页面操作绑定）、§8.8（semantic_graph 接口），M5 将浏览器底层能力与语义图、schema 变量封装为**暴露给 LLM 的引擎函数集**，它是 M6 叶子 agent 执行的前提，现在落地可为 M6/M7 打通"LLM 决策 → 引擎执行"链路。

## What Changes

- 新增**工具函数注册表** `ENGINE_TOOLS`：以工具 schema 形式暴露 open/click/type/select/check/uncheck/scroll/wait/download/upload/semantic_graph/clear_requests/get_response/http_request/extract 共 15 个函数给 LLM（契约 §5.8.1）
- 新增 **`EngineFunctions` 执行实现**：每个函数一个方法，签名与 `docs/specs/M5-engine-functions.md` §5.2 一致，统一返回 `OpResult`（成功/失败 + 错误信息）
- 新增 **ref 解析**：LLM 传来的 `ref`（如 `[1]`）→ ref 映射表 → 引擎侧元素 id → DOM 节点，全程确定性、不信任 LLM；页面状态变化后旧 ref 失效并拒绝调用（契约 §7.8 方案 B）
- 新增**页面操作绑定**：click/type/select/check/uncheck/scroll/wait/download/upload/semantic_graph 等函数作用于"当前页面变量"指向的页面；页面切换由变量指定，LLM 不做页面切换决策（契约 §5.10）
- 新增**变量写入副作用**：`open(url)` 返回页面引用并写入 M3 页面引用类型变量；`extract(ref, 目标)` 提取值经 M3 类型校验后写入变量（契约 §5.3/§5.3.5）
- 新增**错误语义**：函数失败（如 click 失败）→ `OpResult(ok=False, error=...)` 作为工具结果回传 LLM，由 LLM 自行修正，不抛异常中断 agent；致命错误（浏览器崩溃）→ 抛出 `FatalBrowserError` 终止流程（契约 §5.8）
- 支持**函数集可扩展**：新增函数即注册即用，随需求增减（契约 §5.8.1）
- 测试以 **mock 语义图/M3** 为主，覆盖 ref 映射、页面绑定、错误语义，不依赖 M6/M7

## Capabilities

### New Capabilities
- `engine-functions`: 暴露给 LLM 的引擎函数集——工具注册表、函数执行实现、ref 确定性解析、页面操作绑定、变量写入副作用与可分类错误语义，是 M6 叶子 agent 的调用接口

### Modified Capabilities
<!-- 无既有 capability 的需求发生变更 -->

## Impact

- **新增代码**：`webops/engine/`（或等价包）下的工具注册表、`EngineFunctions` 执行实现、ref 映射表、`OpResult` 结果类型与 `FatalBrowserError` 异常（对应 `docs/specs/M5-engine-functions.md` 第 5 章接口契约）
- **依赖方**：M1（浏览器驱动）提供操作/文件/HTTP/DOM 爬取实现；M4（语义图生成）提供 `semantic_graph` 接口；M3（schema 命名空间）提供变量读写、页面变量绑定与类型校验
- **被依赖方**：M6（叶子 agent 执行）将把 `ENGINE_TOOLS` 作为工具定义传给 LLM，并调用 `EngineFunctions` 执行工具；M7（编排器）间接使用
- **测试影响**：单元测试以 mock M4 语义图与 M3 变量读写为主，配合 mock 浏览器即可离线运行；集成测试（可选）使用真实浏览器 + 真实语义图验证函数闭环