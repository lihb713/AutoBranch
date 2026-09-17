# llm-client Specification

## Purpose

为 AutoBranch 提供统一的 OpenAI 兼容 LLM 调用入口，覆盖 LLM 配置管理、多轮工具调用会话、上下文与 token 预算管理以及可分类的错误语义，供叶子 agent 执行（M6）与语义图生成（M4）复用，无依赖、可独立测试。

## Requirements

### Requirement: LLM 配置管理

系统 SHALL 接受调用方提供的 LLM 配置，配置 SHALL 包含三个必填字段：`base_url`（OpenAI 兼容接口地址）、`api_key`（接口鉴权密钥）、`model`（模型名）。系统 SHALL 使用该配置向指定的 base_url 发起请求，且不得将 `api_key` 写入日志或报告。

#### Scenario: 合法配置可发起请求

- **WHEN** 调用方提供包含 base_url、api_key、model 的完整配置并请求一次对话
- **THEN** 系统向该 base_url 发起 LLM 请求，并返回模型的文本回复

#### Scenario: 缺少必填字段的配置被拒绝

- **WHEN** 调用方提供缺少 base_url、api_key 或 model 任一必填字段的配置
- **THEN** 系统拒绝该配置并抛出参数校验错误，不发起任何网络请求

#### Scenario: api_key 不被泄露到日志

- **WHEN** 系统记录请求相关日志且配置中包含 api_key
- **THEN** 日志内容不包含 api_key 明文

### Requirement: OpenAI 兼容协议支持

系统 SHALL 支持至少一种 OpenAI 兼容的对话协议形态：Chat Completions 或 Responses；两种形态均为第一版目标。系统 SHALL 能够解析该协议的响应并提取文本回复或工具调用请求。

#### Scenario: Chat Completions 协议对话成功

- **WHEN** 调用方使用 Chat Completions 兼容端点发起一次不含工具的对话
- **THEN** 系统以 Chat Completions 请求格式访问端点，并解析出模型回复的文本

#### Scenario: Responses 协议对话成功

- **WHEN** 调用方使用 Responses 兼容端点发起一次不含工具的对话
- **THEN** 系统以 Responses 请求格式访问端点，并解析出模型回复的文本

#### Scenario: 响应中无内容时返回空文本

- **WHEN** 端点返回一个不含文本内容、也不含工具调用的成功响应
- **THEN** 系统返回文本为空的结果，不视为错误

### Requirement: 多轮工具调用会话

系统 SHALL 支持 agent 式会话：会话以 system 提示词初始化，可添加用户消息，可声明可调用工具列表；当模型回复包含工具调用请求时，调用方可执行工具并以工具结果回填会话后再次请求，如此循环。每次请求返回的结果 SHALL 区分"纯文本回复"与"工具调用请求"两种形态。工具定义 SHALL 包含 `name`、`description` 与 `parameters`（JSON Schema 格式）三个字段，并随请求一并发送给模型。

#### Scenario: 单轮工具调用

- **WHEN** 会话声明了工具，且模型回复包含一个工具调用请求（含调用 id、工具名与 JSON 参数）
- **THEN** 系统返回该工具调用请求，调用方可据此执行对应工具

#### Scenario: 工具结果回填后再次请求

- **WHEN** 调用方将某工具调用 id 对应的执行结果回填进会话并再次发起请求
- **THEN** 系统把该工具结果作为对话上下文的一部分发送给模型，并返回模型基于该结果给出的回复

#### Scenario: 多轮工具调用循环可用

- **WHEN** 会话经历"请求 → 工具调用 → 回填结果 → 再请求"的多轮循环
- **THEN** 每一轮的工具调用请求 id 与工具结果均正确配对，且上下文在轮次间持续累积、不丢失

#### Scenario: 不含工具时返回纯文本

- **WHEN** 会话未声明任何工具，或模型直接给出文本回复而不请求工具
- **THEN** 系统返回纯文本回复，且不产生任何工具调用请求

#### Scenario: 工具调用参数为非法 JSON

- **WHEN** 模型返回的工具调用参数不是合法 JSON 字符串
- **THEN** 系统按参数解析失败处理并抛出可识别错误，不将非法参数当作合法调用静默通过

### Requirement: 上下文与消息序列累积

系统 SHALL 在会话内按序维护 system 提示词、用户消息与工具结果回填的消息序列；每次请求 SHALL 携带自会话开始以来的完整消息序列（而非仅新增消息），保证模型可见的上下文持续累积、工具结果不丢失。

#### Scenario: 消息按序累积

- **WHEN** 调用方依次添加用户消息并多次请求
- **THEN** 每次请求的报文均按添加顺序包含全部历史消息，且顺序保持不变

#### Scenario: 工具结果保留在上下文中

- **WHEN** 调用方回填某个工具结果后再次请求
- **THEN** 后续请求的报文仍包含该工具结果对应的消息，不会因新请求而丢失

### Requirement: token 统计与预算管理

系统 SHALL 统计会话累计使用的 token 数量，并在每次请求后更新；系统 SHALL 提供查询会话当前累计 token 的方法，以及判断累计 token 是否超过给定预算上限的方法。当单次请求触发的累计 token 超过预算上限时，系统 SHALL 抛出预算超限异常（`LLMBudgetExceeded`），由上层（M6 叶子执行）终止当前叶子。

#### Scenario: token 统计随请求累积

- **WHEN** 调用方在多次请求后查询会话累计 token
- **THEN** 返回的 token 数量等于各次请求 token 消耗的总和，且只增不减

#### Scenario: 未超预算时正常返回

- **WHEN** 会话累计 token 未超过给定预算上限
- **THEN** 请求正常返回结果，不抛出预算相关异常

#### Scenario: 超过预算上限抛出异常

- **WHEN** 某次请求导致会话累计 token 超过给定预算上限
- **THEN** 系统抛出 `LLMBudgetExceeded` 异常，且调用方可据此终止当前叶子执行

### Requirement: 可分类的错误语义

系统 SHALL 将 LLM 调用失败按错误源分为可区分的异常类别，供上层按错误源分流处理（契约 §9.4）：

- 网络层错误（连接失败、DNS 解析失败等）→ `LLMConnectionError`
- API 鉴权失败（api_key 无效、无权限等）→ `LLMAuthError`
- 请求超时 → `LLMTimeoutError`
- token 预算超限 → `LLMBudgetExceeded`

#### Scenario: 网络连接失败抛出连接错误

- **WHEN** 请求因网络不可达或连接被拒绝而失败
- **THEN** 系统抛出 `LLMConnectionError`，调用方可据此判断为程序侧（基础设施）失败并按需重试

#### Scenario: 鉴权失败抛出鉴权错误

- **WHEN** 端点返回鉴权失败（如 401/403）
- **THEN** 系统抛出 `LLMAuthError`，调用方可据此判断为配置问题而非临时故障

#### Scenario: 请求超时抛出超时错误

- **WHEN** 请求在超时阈值内未获得响应
- **THEN** 系统抛出 `LLMTimeoutError`，调用方可据此判断为程序侧失败并决定是否重试

#### Scenario: 预算超限抛出预算异常

- **WHEN** 累计 token 超过预算上限
- **THEN** 系统抛出 `LLMBudgetExceeded`，与网络/鉴权/超时错误类别可被上层区分处理

### Requirement: 流式与非流式响应

系统 SHALL 支持非流式响应作为默认形态（批处理模式）；流式响应为可选能力。非流式请求 SHALL 在一次响应中返回完整结果；流式请求 SHALL 将结果按模型输出分段逐步返回，且最终汇聚的结果与非流式一致。

#### Scenario: 非流式返回完整结果

- **WHEN** 调用方以非流式方式发起请求
- **THEN** 系统在一次调用中返回模型的完整文本回复

#### Scenario: 流式返回分段内容

- **WHEN** 调用方以流式方式发起请求
- **THEN** 系统按模型输出分段返回内容，并最终提供完整的汇聚结果