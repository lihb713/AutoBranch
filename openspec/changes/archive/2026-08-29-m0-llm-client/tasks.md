## 1. 工程骨架与传输层

- [x] 1.1 创建 `webops/llm/` 包结构与模块骨架，验证 `pip install -e .` 后包可导入（`python -c "import webops.llm"` 无报错）
- [x] 1.2 定义传输层接口（发起请求 → 返回状态码 + 响应体），验证接口签名可被 fake 实现与真实实现共同满足
- [x] 1.3 实现基于标准库 `urllib.request` 的默认传输，验证对任意 `base_url` 发起 POST 请求并返回状态码与响应体
- [x] 1.4 实现 FakeTransport（预设响应序列），验证 mock HTTP 测试基础设施可用：拦截请求、返回预设响应

## 2. 配置与数据结构

- [x] 2.1 实现 `LLMConfig` 数据类（`base_url` / `api_key` / `model` 必填），验证缺失任一字段构造时报参数校验错误
- [x] 2.2 实现 `ToolSpec`（`name` / `description` / `parameters` JSON Schema）、`ToolCall`（`id` / `name` / `arguments`）、`LLMResponse`（`text` / `tool_calls`）数据类，验证字段类型与默认值行为符合 M0 spec §5.1/5.3/5.4
- [x] 2.3 验证配置中的 `api_key` 不进入日志输出，测试断言日志内容无明文密钥

## 3. Chat Completions 协议请求与响应解析

- [x] 3.1 实现 Chat Completions 请求构造（`messages` / `tools` / `stream` 等字段），验证用 FakeTransport 捕获请求体后字段结构与顺序正确
- [x] 3.2 实现 Chat Completions 响应解析：提取 `content` 文本与 `tool_calls`，验证纯文本回复与工具调用请求两种形态均能正确解析
- [x] 3.3 验证响应既无文本也无工具调用时返回空文本结果、不视为错误
- [x] 3.4 验证工具调用 `arguments` 为非法 JSON 时抛可识别错误，测试覆盖该分支

## 4. 会话：消息累积与多轮工具调用

- [x] 4.1 实现 `LLMSession`（`config` + `system_prompt` 初始化），验证 `add_user_message` 按序累积消息
- [x] 4.2 实现 `request(tools)` 携带会话内全量消息序列，验证多次请求后报文包含全部历史消息且顺序不变、工具结果不丢失
- [x] 4.3 实现 `add_tool_result(call_id, result)` 回填工具结果，验证"助手请求工具 → 回填 → 再请求"单轮循环正确配对 id
- [x] 4.4 实现多轮工具调用循环，验证多轮循环后上下文持续累积、每轮工具 id 与结果正确配对（集成测试）

## 5. token 统计与预算管理

- [x] 5.1 实现 token 统计：优先取响应 `usage` 累加，缺失时保守估算并标注来源，验证 `token_used()` 随请求只增不减、数值等于各轮累加和
- [x] 5.2 实现 `exceeds_budget(limit)`，验证未超预算时请求正常返回
- [x] 5.3 实现预算超限检测：请求后累计超过上限抛 `LLMBudgetExceeded`，验证调用方可捕获并终止叶子（对应 spec 预算场景）

## 6. 可分类错误语义

- [x] 6.1 实现错误映射：网络/连接异常 → `LLMConnectionError`，验证抛错类别正确且重试语义可被上层区分
- [x] 6.2 实现鉴权失败映射（401/403）→ `LLMAuthError`，验证 FakeTransport 返回 401 时抛错类别正确
- [x] 6.3 实现请求超时 → `LLMTimeoutError`，验证设置短超时并模拟挂起响应时抛错类别正确
- [x] 6.4 验证四类异常（连接/鉴权/超时/预算）可被上层区分捕获，测试覆盖四分支

## 7. Responses 协议适配与流式

- [x] 7.1 实现 Responses 协议请求构造与响应解析，验证通过 FakeTransport 捕获请求体并解析出文本/工具调用
- [x] 7.2 验证 Chat Completions 与 Responses 两种形态共享同一会话与响应结构，切换形态不影响消息累积与工具回填
- [x] 7.3 实现流式请求（可选能力），验证分段返回内容与最终汇聚结果一致（至少非流式验收路径全绿）

## 8. 集成验收与文档同步

- [x] 8.1 编写集成测试：配置 → 多轮工具调用 → 预算检测 → 错误分类全链路，验证 `pytest` 全绿且不依赖真实 API/浏览器
- [x] 8.2 可选冒烟测试：连接任一 OpenAI 兼容端点验证真实请求，作为可跳过验收项
- [x] 8.3 运行 `pytest` 与 lint（如 ruff），验证全部单测 + 集成测试通过、无 lint 告警
- [x] 8.4 同步更新 `docs/contract.md`（若涉及接口语义）与 `docs/specs/M0-llm-client.md`，验证文档与代码实现一致