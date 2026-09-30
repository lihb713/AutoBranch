# llm-streaming-cert-bypass 任务

## 1. LLM 流式解析（protocols.py）

- [x] 1.1 `ChatCompletionsAdapter` 新增 `parse_stream_response(body) -> (LLMResponse, usage)`：SSE 逐行解析，累积 `delta.content`、按 index 归并 `delta.tool_calls` 并拼接 `arguments`，取 usage；最终 arguments 经 `_validate_json_arguments` 校验；单测覆盖 content 分段、工具调用增量拼接、usage 提取、非法 JSON arguments 抛 `LLMProtocolError`、空内容
- [x] 1.2 保持 `parse_chat_stream`/`stream()` 原样（向后兼容）；确认既有 streaming 测试不回归

## 2. 请求路径流式 + 回落 + 端点缓存（session.py）

- [x] 2.1 `LLMSession.request()` 支持形态选择：默认 `stream=True`（chat 协议；responses 恒非流式）；新增内部 `_StreamModeRejected` 信号（HTTP 400/405/422/501 且响应体含 `stream`）；进程级端点缓存 `dict[base_url, mode]`（模块级 + 锁），首次成功/回落成功后写入
- [x] 2.2 `_request_once` 按形态发请求并分流解析（流式 → `parse_stream_response`，否则 `parse_response`）；回落时以另一形态重试一次并更新缓存；单测覆盖：默认流式（fake SSE body）解析正确、端点拒绝流式自动回落非流式、缓存命中不重复回落、responses 协议恒非流式

## 3. 浏览器证书豁免

- [x] 3.1 `BrowserConfig.ignore_https_errors`（默认 False）+ `BrowserDriver.start` 的 `new_context(ignore_https_errors=cfg.ignore_https_errors)`；单测断言开启/关闭时 context 参数
- [x] 3.2 `BrowserOptions` 加 `ignore_https_errors` + `from_dict` + `to_browser_config()`；配置测试默认 False 与覆盖生效

## 4. 文档与验收

- [x] 4.1 更新 `docs/contract.md` §6.1（LLM 请求方式：默认流式 + 自动回落，无配置项）、M0-llm-client spec、M1/browser spec（证书豁免）、README（`browser.ignore_https_errors` 配置）
- [x] 4.2 全量验证：`pytest`、前端 `npm run lint/typecheck/test`、E2E 相关；按 AGENTS.md 提交并推送（中文提交信息）