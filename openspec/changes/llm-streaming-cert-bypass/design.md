# llm-streaming-cert-bypass 设计

## Context

现状：`LLMSession.request()` 全程非流式（`stream=False`），`stream()` 方法存在但未接入执行且不解析 tool_calls（protocols.py `parse_chat_stream` 只取 `delta.content`）；`build_request` 已支持 `stream` 字段，传输层 `urllib.urlopen().read()` 一次性读完整响应体。浏览器 `BrowserDriver.start` 调 `new_context()` 无证书豁免参数，内网自签/私有 CA 站点报 `ERR_CERT_AUTHORITY_INVALID`。

关键简化：工具不需要"真·增量消费"流式——叶子只需最终 content + tool_calls。因此"支持流式"= 发 `stream:true` + 一次性读完整 SSE 响应体 + 按 SSE 格式解析出 `LLMResponse`，无需改传输层为增量读。

## Goals / Non-Goals

**Goals:**
- 主请求路径默认流式、端点拒绝时自动回落非流式（无配置项），按端点缓存已工作形态。
- 流式解析覆盖文本、工具调用增量（拼接 arguments）、usage。
- 浏览器 `ignore_https_errors` 配置（默认关），内网全信任。

**Non-Goals:**
- Responses 协议流式（当前工具不可达该路径）。
- 真·增量流式消费（边到边渲染）；工具只取最终结果。
- Q3 代理支持（留待单独讨论）。

## Decisions

### D1. 请求形态选择：默认流式 + 失败回落 + 端点缓存

- **默认形态**：`stream=True`（chat 协议）。2026 年 OpenAI 兼容端点普遍支持流式（vLLM/Ollama/网关），"只支持流式"正是痛点，默认流式直接命中；"只支持非流式"是极少数，回落兜住。Responses 协议不支持流式解析 → 恒非流式。
- **回落信号**：HTTP 400/405/422/501 **且**响应体（小写）含 `stream` → 抛内部 `_StreamModeRejected` → `request()` 以另一形态重试一次。
- **端点缓存**：进程级 `dict[base_url, mode]`（模块级 + 锁）。首次成功（或回落成功）后写入；后续请求直接复用，不重复探测。
- 为什么不用配置项：用户明确"直接兼容即可"；缓存避免每次叶子重新探测（每叶子一个 LLMSession）。

### D2. 流式解析（chat 协议）

`ChatCompletionsAdapter.parse_stream_response(body) -> (LLMResponse, usage)`：
- 逐行解析 `data:` 事件，跳过 `[DONE]` 与空/非 JSON。
- 累积 `choices[0].delta.content` → text。
- `delta.tool_calls` 按 `index` 归并：首次出现取 `id`/`name`，逐段拼接 `function.arguments`。
- 末段 `choices[0].finish_reason` 可忽略；`usage` 取任意 chunk 顶层 `usage`（OpenAI 流式在最终 chunk 提供）。
- 最终 `arguments` 经 `_validate_json_arguments` 校验（非法 → `LLMProtocolError`）。
- 现有 `parse_chat_stream`（content 分段列表）与 `stream()` 方法保持原样（向后兼容，未使用路径）。

### D3. 传输层与错误分类

- `UrllibTransport` 不改：`urlopen().read()` 在 SSE 流结束后返回完整 body（服务器发完 `[DONE]` 关闭连接）。
- 回落信号检测放在 `LLMSession._request_once`：拿到 `(status, body)` 后，先判 401/403（现有），再判"流式被拒"信号（4xx + 含 stream），最后按形态解析。

### D4. 浏览器证书豁免

- `BrowserConfig` 增 `ignore_https_errors: bool = False`；`BrowserDriver.start` 的 `new_context(ignore_https_errors=cfg.ignore_https_errors)`。
- `BrowserOptions`（autobranch/config.py）同步字段 + `from_dict` + `to_browser_config()`。
- 安全边界：默认关；文档注明仅内网/可信环境开启。

## Risks / Trade-offs

- **回落信号启发式**：个别"只支持非流式"端点报错文案不含 `stream` 时回落不触发（失败）→ 覆盖率足够但不完备；备选"首启双探针"更准但首次多一次调用，暂不采用。
- **默认流式**：对已工作端点需确认其支持 `stream:true`（OpenAI 兼容普遍支持）；流式解析 bug 风险由单测覆盖。
- **证书豁免安全**：开启后所有 HTTPS 证书不校验 → 仅内网/可信环境；默认关。

## Migration Plan

无数据迁移；纯行为/配置扩展。`ignore_https_errors` 缺省 False，旧配置兼容。

## Open Questions

- 无阻塞项。Q3 代理支持留待后续单独讨论（不在本 change 范围）。