## Why

WebOps 的所有 LLM 交互（叶子 agent 的 Action/Condition 执行、语义图生成）都需要一个统一的 LLM 调用能力，但当前代码库中尚无任何 LLM 客户端实现。依据 `docs/contract.md` §6，用户需能配置任意 OpenAI 兼容端点（base_url + api_key + 模型名）以发起对话，这是 M6（叶子 agent）与 M4（语义图生成）共同依赖的地基模块，**无依赖、最早实现**，现在落地它可为后续模块打通调用链。

## What Changes

- 新增 LLM 客户端模块，作为 WebOps 全部 LLM 交互的唯一入口
- 新增 LLM 配置管理：支持用户配置 `base_url` + `api_key` + `model`（契约 §6.1）
- 新增 Chat Completions / Responses 两种 OpenAI 兼容协议形态的请求能力（契约 §6.1）
- 新增多轮工具调用会话：system 提示词 + 用户/工具消息序列 + 工具定义 + 工具结果回填，支持"助手请求工具 → 回填结果 → 再次请求"的循环（契约 §5.7.2）
- 新增上下文管理：消息序列累积、token 统计与预算超限检测（契约 §5.7.2.1）
- 新增错误分类语义：网络错误 / 鉴权失败 / 超时 / 预算超限分别抛出可分类异常，供上层按错误源分流（契约 §9.4）
- 支持流式与非流式响应（第一版以非流式为主，流式为可选能力，契约 §6.2）
- 引入 Mock HTTP 测试策略，保证模块不依赖浏览器与行为树、可独立测试

## Capabilities

### New Capabilities
- `llm-client`: 提供统一的 OpenAI 兼容 LLM 调用能力——配置管理、多轮工具调用会话、上下文与 token 预算管理、可分类的错误语义，被 M6 叶子 agent 与 M4 语义图生成复用

### Modified Capabilities
<!-- 无既有 capability 的需求发生变更 -->

## Impact

- **新增代码**：`webops/llm/` 下的 LLM 配置、会话、响应结构、工具定义与错误类型（对应 `docs/specs/M0-llm-client.md` 第 5 章接口契约）
- **被依赖方**：M6（叶子 agent 执行）与 M4（语义图生成 LLM 填充阶段）将通过本模块发起所有 LLM 调用；M9b 可注入 LLM 配置
- **外部依赖**：需引入 HTTP 客户端（可选用标准库 `urllib` 或 `requests`，避免引入 `openai` SDK 以保持对任意 OpenAI 兼容端点的透明支持）
- **测试影响**：全部测试基于 Mock HTTP 拦截，不依赖真实 API 密钥，可离线运行