# M0 · LLM 客户端 Spec

> 依据契约 `docs/contract.md` §6（与 LLM 的对接）、§5.7.2（叶子节点 agent 式执行）、§8.5（语义图 LLM 填充阶段）。

## 1. 概述

封装 OpenAI 兼容接口，为 AutoBranch 提供统一的 LLM 调用能力。它是所有 LLM 交互的唯一入口，被叶子 agent 执行（M6）与语义图生成（M4）复用。**无依赖、最早实现，可独立测试。**

## 2. 功能范围

| 功能 | 说明 | 契约依据 |
|---|---|---|
| LLM 配置管理 | 用户配置 base_url + api_key + 模型名 | §6.1 |
| Chat Completions / Responses 兼容 | 第一版支持 OpenAI 兼容接口 | §6.1 |
| 多轮工具调用会话 | agent 式会话：system + 消息序列 + 工具定义 + 工具结果回填 | §5.7.2 |
| 上下文管理 | 维护对话消息序列、token 预算与截断 | §5.7.2.1 |
| 流式/非流式 | 批处理模式，支持非流式响应（可选流式） | §6.2 |

**非目标（第一版）**：
- 不接入 Anthropic / Gemini 等非 OpenAI 兼容厂商
- 不做模型自发现 / 模型路由

## 3. 数据依赖

### 3.1 输入
- **LLM 配置**：`{ base_url, api_key, model, timeout }`（来自统一配置 `autobranch.config.json`，经 `AutoBranchConfig.load().to_llm_config()` 构建；`api_key` 可直接写入配置文件 `llm.api_key`，环境变量 `AUTOBRANCH_LLM_API_KEY` 存在时优先，见 contract §6.3；M9b 亦可注入）
- **会话参数**：`system_prompt`、用户/工具消息序列、可调用工具（函数 schema）列表

### 3.2 输出
- **助手消息**：文本回复或工具调用请求（`tool_calls`）
- **工具调用结果回填**：将工具执行结果作为 `tool` 角色消息追加回会话

## 4. 单元间依赖

- **依赖**：无
- **被依赖**：
  - M4（语义图生成）— LLM 填充 purpose / related-to 打分
  - M6（叶子 agent 执行）— Action/Condition 的 agent 式决策

## 5. 接口契约

### 5.1 配置结构

```python
@dataclass(frozen=True)
class LLMConfig:
    base_url: str          # OpenAI 兼容接口地址（必填，缺失抛 ValueError）
    api_key: str           # 接口鉴权密钥（必填；不进入日志/报告）
    model: str             # 模型名（必填）
    session_id: str | None = None   # 可选：稳定会话标识（x-opencode-session 请求头）
```

### 5.2 会话接口

```python
class LLMSession:
    def __init__(self, config: LLMConfig, system_prompt: str,
                 transport: Transport | None = None,
                 protocol: Literal["chat", "responses"] = "chat",
                 budget_limit: int | None = None,
                 timeout: float = 60.0,
                 session_id: str | None = None): ...   # session_id 覆盖 config.session_id
    def add_user_message(self, content: str) -> None: ...
    def add_tool_result(self, call_id: str, result: ToolResult | str) -> None: ...
    def request(self, tools: list[ToolSpec] | None = None, stream: bool = False) -> LLMResponse: ...
    def stream(self, tools: list[ToolSpec] | None = None) -> list[str]: ...  # 流式分段
    def token_used(self) -> int: ...
    def exceeds_budget(self, limit: int) -> bool: ...
```

**request() 行为**：携带会话内全量消息序列（system + 用户 + 助手 + 工具结果，全量累积）；
解析响应后自动将助手回复（含 tool_calls）追加为上下文（OpenAI 要求 tool 消息紧跟
对应 assistant tool_calls 消息）；请求后读取 usage 累计 token，超预算抛异常。
**会话标识**：每个会话生成一个稳定的 `x-opencode-session` 请求头（`session_id` 显式值、
否则 `config.session_id`、否则自动 UUID）；同一会话内多轮请求共用同一 ID，供网关
路由与提示缓存优化（OpenCode Go 网关缺失该头返回 400 `MissingSessionID`）。

### 5.3 响应结构

```python
@dataclass(frozen=True)
class LLMResponse:
    text: str = ""                      # 纯文本回复（无内容时为空字符串，非 None）
    tool_calls: list[ToolCall] = []     # 工具调用请求（无则为空列表）

@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str                      # 参数 JSON 字符串（非法 JSON 抛 LLMProtocolError）
```

### 5.4 工具定义

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict = {}               # JSON Schema（默认空 dict）
```

### 5.5 传输层与协议适配

```python
class Transport(Protocol):            # 传输层接口（设计 D2）
    def request(self, url: str, headers: dict[str, str],
                body: bytes, timeout: float) -> TransportResponse: ...

class UrllibTransport(Transport):     # 默认实现：标准库 urllib，带 User-Agent 头
    ...

# 协议适配（设计 D3）：Chat Completions（/chat/completions）与 Responses（/responses）
# 映射到同一内部 Message 序列与同一 LLMResponse 结构，差异收敛在适配层。

# 请求头：User-Agent 为自定义（autobranch-llm-client/0.1，非 urllib 默认）；
# x-opencode-session 由 LLMSession 按会话注入（见 §5.2），传输层透传调用方 headers。
```

### 5.6 token 统计

- 优先取响应 `usage` 累加（兼容 Chat Completions 的 prompt/completion/total 与
  Responses 的 input/output/total 两种字段形态）
- `usage` 缺失时按消息内容长度保守估算（非空白字符数/3 + 1），标注为 estimated

### 5.7 错误语义
- 网络错误 / API 鉴权失败 / 超时 → 抛出可分类异常（`LLMConnectionError` / `LLMAuthError` / `LLMTimeoutError`），由调用方按错误源分流（§9.4）
- token 预算超限 → 抛出 `LLMBudgetExceeded`，由 M6 终止叶子
- 响应无法解析（格式错误 / 工具参数非法 JSON）→ `LLMProtocolError`

## 6. 验收标准

- [x] 配置任意 OpenAI 兼容 base_url + api_key + 模型名可发起请求
- [x] 每个会话发送稳定的 `x-opencode-session` 请求头（同一会话多轮一致；配置可显式指定）
- [x] 支持 Chat Completions 与 Responses 两种协议形态（Mock 测试均覆盖）
- [x] 多轮工具调用：助手请求工具 → 回填结果 → 再次请求，循环可用
- [x] 上下文正确累积，工具结果不丢失（request 自动追加助手消息）
- [x] token 统计准确（usage 优先、缺失估算），预算超限可检测并抛异常
- [x] 错误按类别抛出，可被上层区分处理
- [x] 流式请求（可选能力）：SSE 分段解析，汇聚结果与非流式一致

## 7. 测试策略

- **Mock HTTP**（`tests/fake_transport.py`）：`FakeTransport` 拦截请求、返回预设响应序列，验证请求体格式、工具回填正确性（独立于真实网络）
- **真实 API 冒烟**（可选，`tests/test_smoke.py`）：经环境变量注入密钥后连接 OpenAI 兼容端点验证（未配置自动跳过）。已验证 **OpenCode Go** 端点：
  `AUTOBRANCH_LLM_BASE_URL=https://opencode.ai/zen/go/v1`、`AUTOBRANCH_LLM_MODEL=deepseek-v4-flash`，含文本回复与工具调用两条路径
- **单元测试**：消息序列累积、token 统计、异常分类、协议解析（协议/传输/会话均可离线测试）
- **独立性**：不依赖浏览器、不依赖行为树，可单独运行全部测试
## 请求重试（已实现）

`LLMConfig` 支持 `retry_times`（默认 2）/ `retry_delay`（默认 1.0）；`LLMSession.request` 对**瞬时失败**（连接错误 / 超时 / HTTP 429 / 5xx）指数退避重试（1s→2s）。重试只在成功时才累积上下文（不重复消息）；401/403 鉴权、预算超限不重试。
