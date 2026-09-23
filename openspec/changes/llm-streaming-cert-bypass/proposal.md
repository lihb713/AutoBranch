# llm-streaming-cert-bypass 提案

## Why

实际部署中遇到两类兼容性问题：① 部分 LLM 接口**只接受流式请求**（`stream: true`），当前执行路径全程走非流式（`LLMSession.request()` 默认 `stream=False`），这类端点会拒绝或挂起，导致叶子无法执行；② 内网环境访问自签名/私有 CA 站点时 Chromium 报 `ERR_CERT_AUTHORITY_INVALID`，当前浏览器 context 无证书豁免选项，无法访问。二者都是"默认行为不兼容特定环境"的适配问题，需要默认兼容两种请求方式（不引入用户配置项）+ 一个证书豁免开关（内网用）。

## What Changes

- **LLM 流式自动兼容（无配置项）**：
  - 主请求路径（`LLMSession.request`）支持流式：发 `stream: true` 后读取完整响应体并按 SSE 格式解析（`chat.completion.chunk`：累积 `delta.content`、逐段拼接 `delta.tool_calls[].function.arguments`、`usage` 取末段 `final`），产出与现在完全一致的 `LLMResponse`（content + tool_calls）。
  - **默认流式**（业界 OpenAI 兼容端点普遍支持），遇端点明确拒绝流式（HTTP 400/405/422/501 且响应体提及 `stream`）→ 自动回落非流式重试一次；成功后**按端点缓存**已工作的模式（进程级，避免每次叶子重复探测）。
  - 不引入 `llm.stream` 配置项；Responses 协议暂不支持流式（当前工具不可达该路径），维持非流式。
  - 现有非流式端点行为不变（两者都支持时流式正常解析）。
- **浏览器证书豁免配置**：
  - `BrowserConfig`/`BrowserOptions` 新增 `ignore_https_errors: bool = False`，`new_context(ignore_https_errors=...)` 传入——开启后**关闭所有 HTTPS 证书校验**（自签/私有 CA/中间人一律信任），供内网环境使用。
  - 配置项：`autobranch.config.json` → `browser.ignore_https_errors: true`。
  - 文档注明安全边界（仅内网/可信环境）。

**BREAKING**：无（默认流式对已工作端点兼容；证书豁免默认关闭，行为不变）。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `llm-client`: LLM 会话请求 SHALL 支持流式（SSE）与非流式两种请求方式，默认流式并在端点拒绝时自动回落非流式（无配置项，按端点缓存模式）；流式解析覆盖 content 与工具调用增量。
- `browser-plugin`: 浏览器会话 SHALL 支持通过配置关闭 HTTPS 证书校验（`ignore_https_errors`），供内网/私有 CA 环境访问。

## Impact

- **LLM 层**：`autobranch/llm/protocols.py`（SSE 流式响应解析：content + tool_calls 增量 + usage）、`autobranch/llm/session.py`（`request()` 支持流式 + 自动回落 + 按端点缓存模式）、`autobranch/llm/transport.py`（读完整流式响应体，无需增量消费；分类"流式被拒"信号）。
- **浏览器层**：`autobranch/plugins/browser/driver/config.py`（`ignore_https_errors`）、`driver.py`（`new_context(ignore_https_errors=...)`）、`autobranch/config.py`（`BrowserOptions.ignore_https_errors` + `to_browser_config()`）。
- **文档**：`docs/contract.md` §6.1（LLM 配置/请求方式）、M0-llm-client spec、M1-behavior-tree-parser/browser spec、README（证书豁免配置）。
- **测试**：流式解析单测（content/tool_calls/usage）、回落与端点缓存单测、证书豁免 API/集成测试。

**依赖**：无（独立能力扩展；Q3 代理问题留待后续单独讨论）。