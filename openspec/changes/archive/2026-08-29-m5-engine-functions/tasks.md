## 1. 基础结构与结果类型

- [x] 1.1 创建 M5 模块包结构（工具 schema、EngineFunctions、ref 映射、OpResult、异常定义），验证包可导入、`pytest` 收集到该模块测试
- [x] 1.2 定义 `OpResult` 结果类型（ok/error 字段，成功与失败两种构造）与 `FatalBrowserError` 异常，验证对 OpResult 成功/失败用例的单元测试通过
- [x] 1.3 定义 `ToolSpec` 工具 schema 结构（name/description/parameters JSON Schema），验证 schema 序列化为 LLM 可解析的工具定义 JSON

## 2. 工具函数注册表

- [x] 2.1 实现 `ENGINE_TOOLS` 注册表，列出 open/click/type/select/check/uncheck/scroll/wait/download/upload/semantic_graph/clear_requests/get_response/http_request/extract 共 15 个函数的工具 schema，验证断言注册表长度为 15 且每个函数名/参数与契约签名一致（对照 docs/specs/M5-engine-functions.md §5.1/§5.2）
- [x] 2.2 实现注册表到执行实现的分发：按函数名调用 EngineFunctions 对应方法，验证对每个函数名的分发单元测试通过
- [x] 2.3 验证函数集可扩展：追加一个测试用新函数后无需改既有代码即可被分发与暴露，验证扩展性测试通过

## 3. ref 确定性解析

- [x] 3.1 实现 ref 映射表：维护 ref ↔ 引擎侧元素 id ↔ DOM 节点的确定性映射（构造注入 M1 DOM 能力），验证合法 ref 解析到对应节点的单元测试通过
- [x] 3.2 实现无效 ref 拒绝：不在映射表中的 ref 返回 `OpResult(ok=False)` 且不执行任何操作，验证无效 ref 测试通过
- [x] 3.3 实现过期 ref 拒绝：语义图快照更新/页面状态变化后作废旧 ref，旧 ref 调用被拒，验证"过期 ref 被拒"测试通过（对照契约 §7.8 方案 B）
- [x] 3.4 实现 ref 映射表随语义图生成刷新（新快照生成时作废旧 ref 并登记新 ref），验证"新快照生成后旧 ref 失效"的集成性单元测试通过

## 4. 页面操作绑定

- [x] 4.1 实现当前页面变量的读写通道（注入 M3 变量能力），从当前页面变量解析出目标 page 对象，验证"无当前页面变量时操作函数返回 ok=False"的测试通过
- [x] 4.2 实现操作类函数（click/type/select/check/uncheck/scroll/wait/download/upload）绑定当前页面变量指向的页执行，验证 mock 浏览器下各函数作用于正确页面的绑定测试通过
- [x] 4.3 实现多页面变量场景：切换当前页面变量后操作目标随之改变，验证多页面变量绑定测试通过（对照契约 §5.10）

## 5. 各引擎函数执行实现

- [x] 5.1 实现 `open(url)`：调用 M1 打开页面，返回页面引用并写入 M3 页面引用类型变量，验证 open 成功写入变量、失败返回 ok=False 的测试通过
- [x] 5.2 实现 `semantic_graph(scope, lod)`：委托 M4 语义图生成（作用于当前页面），无缓存、每次完整生成，验证 mock M4 下成功/失败两种结果回传的测试通过
- [x] 5.3 实现 HTTP 形态 A：`clear_requests()` 清理页面请求记录、`get_response(method, url_pattern)` 读取匹配请求响应，验证清理后无匹配返回 ok=False、匹配返回响应的测试通过
- [x] 5.4 实现 HTTP 形态 B：`http_request(method, url, headers, body)` 发起独立请求（不经页面、认证经参数显式提供），验证 mock HTTP 下请求按参数发出且不携带页面会话状态的测试通过
- [x] 5.5 实现 `extract(ref, target)`：提取目标元素值并写入 M3 变量，写入前经 M3 类型校验，验证提取成功写入、类型不匹配不写入返回 ok=False 的测试通过
- [x] 5.6 实现 `wait(condition)` 与 `scroll(direction)` 的 Playwright 封装（作用于当前页面），验证 mock 浏览器下行为正确、失败返回 ok=False 的测试通过

## 6. 错误语义与集成

- [x] 6.1 实现普通失败回传：所有非致命函数失败返回 `OpResult(ok=False, error=...)` 且不抛异常，验证错误语义测试通过（对照 docs/specs/M5-engine-functions.md §5.5）
- [x] 6.2 实现致命错误处理：捕获 M1 不可恢复异常（浏览器崩溃等）并抛 `FatalBrowserError`，验证致命错误测试通过
- [x] 6.3 集成测试（可选）：真实浏览器 + 真实语义图跑通"open → semantic_graph → click → extract"闭环，验证集成测试通过（标记 integration）
- [x] 6.4 运行模块全部测试（`pytest` 含 integration 标记可选）与代码检查，验证 M5 单元测试全部通过且不依赖 M6/M7 模块
- [x] 6.5 同步更新 `docs/contract.md` 相关章节与 `docs/specs/M5-engine-functions.md`，验证文档与实现一致