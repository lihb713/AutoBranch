# M6 · 叶子 agent 执行 Spec

> 依据契约 `docs/contract.md` §5.7.2（叶子节点 agent 式执行）、§5.7.2.1（引擎与 LLM 边界/终止条件）、§5.5（断言求值）、§9.4（错误分类）、§9.6（多轮定位）、§9.7（定位终止条件）。
>
> **实现状态：已实现 ✅**（OpenSpec change `m6-leaf-agent`，2026-08）。代码位于 `webops/leaf_agent/`，测试位于 `tests/leaf_agent/`（含 `tests/leaf_agent_helpers.py` 共享假引擎/慢传输构造器）。本文件已与实现同步；涉及契约语义的实现细节见「与契约的接口细节」一节，供统一更新 `docs/contract.md`。

## 1. 概述

实现 **Action / Condition 叶子节点的 agent 式执行**：将节点自然语言描述 + 当前语义图提供给 LLM，LLM 自主决定调用哪些引擎函数（M5），引擎只做兜底（终止条件 + 错误日志）。这是 LLM 有界代理（§2 单节点执行层）的核心。**依赖 M0（LLM）+ M5（引擎函数）。**

## 2. 功能范围

| 功能 | 说明 | 契约依据 | 实现 |
|---|---|---|---|
| Action agent 执行 | 描述 + 语义图 → LLM 自主调用引擎函数 → 返回成功/失败 | §5.7.2 | ✅ `execute_leaf` → action 路径 |
| Condition agent 执行 | 描述 + 语义图 → LLM 判断真伪 → 返回确定布尔值 | §5.5/§5.7.2 | ✅ `execute_leaf` → condition 路径 |
| 多轮定位 | LLM 多次调用 semantic_graph（缩小/放大）定位目标 | §9.6 | ✅ semantic_graph 作为普通工具注入，零专用逻辑 |
| 引擎兜底 | 终止条件：轮数上限/连续无进展/单叶子超时 | §5.7.2.1 | ✅ `terminator.py` + 驱动循环内检测 |
| 错误边界 | 函数失败归 LLM；致命错误归引擎 | §5.7.2.1/§9.4 | ✅ `OpResult(ok=False)` 回传 / `FatalBrowserError` 终止 |
| 提示词设计 | 节点描述 + 语义图 → 可靠决策的提示词（空间方位感知 + get/set 变量语义 + 「何时获取最新语义图」自主决策） | §10.1-5 | ✅ `prompts.py`（版本化 `PROMPT_VERSION="1.4"`） |

## 3. 数据依赖

### 3.1 输入
- **节点描述**：Action 的动作自然语言 / Condition 的条件自然语言
- **当前语义图**（经 M5 semantic_graph 获取）：执行开始时由引擎预取一次（scope=full、LOD=2，可配置），连同节点描述注入用户消息；后续由 LLM 经 `semantic_graph` 工具按需多次获取（多轮定位）
- **LLM 会话**（M0）：agent 多轮工具调用
- **引擎函数集**（M5）：`ENGINE_TOOLS` 注册表作为会话工具声明

### 3.2 输出
- **Action 结果**：`Success | Failure`（叶子节点状态）
- **Condition 结果**：确定的布尔值
- **执行追踪数据**：`LeafTrace`（LLM 输入/推理过程/决策/工具调用序列/终止条件，供 M8 回溯报告）
- **错误分类**：LLM 侧失败 / 程序侧失败（供报告分流）

## 4. 单元间依赖

- **依赖**：
  - M0（LLM 客户端）— agent 会话（`LLMSession` + `ENGINE_TOOLS` 工具声明）
  - M5（引擎函数层）— `EngineFunctions.call(name, arguments)` 分发入口、`semantic_graph`
- **被依赖**：
  - M7（编排器）— 触发叶子执行、获取结果（`execute_leaf`）
  - M8（报告机制）— 读取执行追踪数据（`LeafTrace` 复用 M8 定义）

## 5. 接口契约

### 5.1 叶子执行接口（已实现）

```python
def execute_leaf(node: ActionNode | ConditionNode, ctx: LeafContext) -> LeafResult: ...

@dataclass(frozen=True)
class LeafContext:
    config: LLMConfig                          # M0 LLM 配置
    engine: EngineFunctions                    # M5 引擎函数（构造注入）
    session_factory: Callable[[LLMConfig, str], LLMSession] | None = None  # 测试注入假传输
    tools: list[ToolSpec] | None = None        # 默认 M5 ENGINE_TOOLS
    max_rounds: int = 10                       # 轮数上限（§5.7.2.1 ①）
    no_progress_rounds: int = 2                # 连续无进展阈值（§9.7 ②）
    timeout: float | None = 120.0              # 单叶子墙钟超时（None 不检测）
    session_timeout: float = 60.0              # 单次 LLM 请求超时
    initial_graph_scope: str = "full"          # 初始语义图范围
    initial_graph_lod: int = 2                 # 初始语义图 LOD

@dataclass(frozen=True)
class LeafResult:
    status: Literal["success", "failure"]
    bool_value: bool | None                   # Condition 专有
    error_source: Literal["llm", "program"] | None  # 失败时
    trace: LeafTrace                          # 复用 M8 `webops/reporting/models.py::LeafTrace`
```

**`LeafTrace` 对齐说明**：`trace` 字段直接复用 M8 定义的 `LeafTrace`（`llm_input`/`llm_reasoning`/`decision`/`calls`/`terminator`），其字段是 M6 spec 需求（`llm_input`/`llm_reasoning`/`calls`/`terminator`）的超集，无需重复定义。M6 内部累积的 `ToolCallRecord`（含时间戳，见下）在写入 `LeafTrace.calls` 前经 `to_m8()` 转为 M8 的 `ToolCallRecord`。

```python
@dataclass(frozen=True)
class ToolCallRecord:          # M6 内部累积 + 序列化支持
    name: str
    arguments: dict | None
    result: str | None
    success: bool | None
    timestamp: float           # epoch 秒
    # to_dict() / from_dict() 序列化往返；to_m8() 转 M8 结构（去时间戳）
```

### 5.2 agent 式执行流程（§5.7.2，已实现）

```
输入: 节点描述 + 当前语义图（引擎预取一次）
  → 构建 M0 会话（系统提示词 + ENGINE_TOOLS 工具声明）+ 用户消息（描述 + 语义图）
  → 循环: session.request(tools) → 工具调用则经 EngineFunctions.call 执行
        → OpResult 作为工具结果 add_tool_result 回填 → 再 request
  → 直到返回纯文本回答（解析最终结果） / 触发终止条件
输出: Action=成功/失败; Condition=确定布尔值
```

- 最终回答标记约定（`parse_final_decision` 解析）：Action 为 `结果: 成功`/`结果: 失败`；Condition 为 `结果: 真`/`结果: 假`（确定判断），`结果: 失败` 表示无法确定 → LLM 侧失败。兼容英文标记（success/failure/true/false）与 JSON 结构化结果（`{"status": ...}`/`{"bool_value": ...}`）。

### 5.3 叶子终止条件（引擎兜底，§5.7.2.1，已实现）

任一触发 → 终止叶子 → 记为 LLM 侧失败 → 沿行为树传播：
1. **LLM 对话轮数上限**：`ctx.max_rounds`（默认 10 轮工具调用），第 N+1 轮请求即终止，`terminator="round_limit"`
2. **LLM 连续 N 轮无进展**：`ctx.no_progress_rounds`（默认 2），对连续多轮的「函数名+参数+结果」指纹比较，`terminator="no_progress"`
3. **单叶子执行超时**：`ctx.timeout`（默认 120s，墙钟计时），`terminator="timeout"`

### 5.4 定位终止条件（§9.7，叶子终止的子集，已实现）

二选一先触发 → 定位失败：
1. 轮数上限（超过 5 轮）→ 由统一轮数上限覆盖（默认 10，可配置为 5）
2. 结果未变检测（连续 2 轮相同判断但无法确认）→ 由 `no_progress_rounds=2` 覆盖
3. token 预算超限 → M0 `LLMBudgetExceeded` → LLM 侧失败，`terminator="budget"`

多轮定位无专用逻辑：`semantic_graph` 作为 M5 普通工具暴露给 LLM，缩小/放大/回溯全部由 LLM 多次调用（不同 scope/LOD）自主完成（§9.6 搜索权归 LLM）。

### 5.5 错误边界（§5.7.2.1/§9.4，已实现）

- **LLM 侧失败**（`error_source="llm"`）：三类终止条件、决策不可解析、Action 报告的失败、`LLMBudgetExceeded`、其他 LLM 错误 → 重试无意义，报告用户提示补文档/CSS
- **程序侧失败**（`error_source="program"`）：`FatalBrowserError`（浏览器崩溃/context 关闭，`terminator="fatal_error"`）、`LLMConnectionError`（`terminator="llm_connection"`）、`LLMTimeoutError`（`terminator="llm_timeout"`）→ 重试有意义（由外层处理）
- **函数失败回传**（agent 语义）：`OpResult(ok=False)` 作为工具结果回传 LLM，由其自行修正（换函数/换元素/重新定位/放弃）；引擎只统计轮数、不判断该不该重试
- **Condition 确定布尔判断**（真/假）：正常节点结果，`error_source=None`（非错误）

## 6. 验收标准（全部已实现并通过测试 ✅）

- [x] Action 叶子执行：LLM 能结合描述+语义图正确调用引擎函数并返回结果
- [x] Condition 叶子执行：LLM 返回确定布尔值作为节点状态依据
- [x] 多轮定位可用：LLM 可多次调用 semantic_graph 缩小/放大
- [x] 三类终止条件全部生效，触发后叶子终止并标记 LLM 侧失败
- [x] 函数失败回传 LLM 后，LLM 可修正并继续（agent 语义）
- [x] 致命错误抛至引擎，终止流程
- [x] 执行追踪数据完整（供回溯报告）
- [x] mock M5 下可完整测试 agent 决策与终止逻辑

## 7. 测试策略（已实现，测试位于 `tests/leaf_agent/`）

| 测试文件 | 覆盖 |
|---|---|
| `test_models.py` | ToolCallRecord 序列化往返/非 JSON 参数/`to_m8` 对齐；LeafResult/LeafTrace 字段齐全 |
| `test_prompts.py` | 提示词渲染确定性/版本号/角色区分；`parse_final_decision` 全标记解析与异常 |
| `test_executor_action.py` | Action 驱动循环（2.1/2.2/2.3/2.4）、决策序列与追踪、函数失败回传修正（5.1）、节点类型分派（1.3） |
| `test_executor_condition.py` | Condition 真/假/无法确定、推理期间不调用操作函数、节点类型分派 |
| `test_termination.py` | 轮数上限/连续无进展/单叶子超时、定位终止子集覆盖（3.1-3.4） |
| `test_errors.py` | 致命错误分流（5.2）、LLM 连接/超时/预算分类、默认分类边界（5.3） |
| `test_multi_round_location.py` | 多轮定位缩小/放大后操作（6.1） |
| `test_regression.py` | 决策序列回归、提示词金样本回归、Action+Condition 串联冒烟（6.3/6.4） |

- **mock 策略**：mock M0 为固定响应 LLM 桩（`tests/fake_transport.py` 复用 + `tests/leaf_agent_helpers.py` 新增 `SlowTransport` 慢响应桩），mock M5 为 `StubEngine`（按函数名返回预设 `OpResult` 序列）；**不依赖 M7**。
- 测试数：42 个（`tests/leaf_agent/`），全部经 `webops` conda 环境 `pytest` 通过；全库 558 passed, 3 skipped；`ruff check .` 无告警。
- 集成测试（真实浏览器 + 真实语义图 + mock LLM 桩）留待 M7 编排器集成验收。

## 8. 与契约的接口细节（待统一更新 contract.md）

1. **`LeafTrace` 对齐 M8**：`execute_leaf` 输出 `trace` 直接复用 M8 定义的 `LeafTrace`（`webops/reporting/models.py`），其 `decision` 字段由 M6 填充为 LLM 最终回答文本；`calls` 为 M8 `ToolCallRecord` 序列（M6 内部记录的时间戳经 `to_m8()` 去除）。**注意：M8 的 `ToolCallRecord` 不含时间戳字段**——若需在报告中展示调用时间，需跨模块在 M8 `ToolCallRecord` 增加可选 `timestamp` 字段（本次未改 M8）。
2. **初始语义图预取**：引擎在驱动循环开始前预取一次 `semantic_graph(scope=full, lod=2)`（可配置），与节点描述一并作为用户消息注入；预取失败不终止，以错误说明文本注入，由 LLM 自行决策（如先 `open` 页面）。此预取不计入 `LeafTrace.calls`（calls 仅含 LLM 发起的工具调用）。
3. **最终回答标记约定**：Action `结果: 成功`/`结果: 失败`；Condition `结果: 真`/`结果: 假`（确定判断）、`结果: 失败`（无法确定→LLM 侧失败）。契约 §5.5「返回确定的布尔值（结构化结果）」在本模块以结果标记行实现（兼容 JSON）。
4. **错误来源默认分类**（design D4 明确化）：程序侧仅两类（`FatalBrowserError` 与 `LLMConnectionError`/`LLMTimeoutError`），其余失败（含全部终止条件）一律 `error_source="llm"`；**例外：Condition 的确定布尔判断（真/假）是正常节点结果，`error_source=None`**（不是错误，flow 沿树走分支）。
5. **`terminator` 取值集合**：`round_limit`/`no_progress`/`timeout`/`budget`（LLM 侧终止）与 `fatal_error`/`llm_connection`/`llm_timeout`/`llm_error`（错误中断）；正常完成或决策不可解析为 `None`。
6. **`LeafContext.engine` 注入**（design D6）：M6 不构造 `EngineFunctions`，由 M7/后端注入（依赖 M5 构造注入约定）；`session_factory` 供测试注入假传输，默认按 `config` + `session_timeout` 构建真实会话。
7. **轮数语义**：`max_rounds` 指 LLM 工具调用轮数上限，第 `max_rounds+1` 轮请求即终止（前 `max_rounds` 轮完整执行并回填）。
8. **提示词版本化**：`PROMPT_VERSION="1.4"`，变更提示词须递增版本号并通过回归测试（`tests/leaf_agent/test_regression.py` 金样本）。v1.1 起新增空间方位感知（结合语义图 `(页面方位)` 标注理解位置指令）与「何时获取最新语义图」的自主决策引导：操作可能改变页面布局/关键信息时操作前获取最新；操作或判断失败时重新获取最新；其余情况可复用当前语义图，不强制每次获取，引擎以 ref stale 兜底（M5）。v1.2 新增变量 get/set 语义：`{{get:this/...}}` 已被程序在叶子执行前替换为真实值（LLM 无需处理）；`{{set:this/...}}` 声明本动作可写变量集，LLM 提取值后调 extract 且 target 须取自声明集（未声明目标被拒）。v1.3 类型化 set 标注（`{{set:page:...}}`/`{{set:string:...}}` 提示存页签/存文本、选 open(save_to)/get_url）。v1.4 类型标注并入 TYPE_REGISTRY 英文 token：`{{set:page_ref:...}}`（open save_to 存页签）、`{{set:str:...}}`（extract 或 get_url 存文本）、其余 token（int/float/bool）提示「提取并转换后存入」。
