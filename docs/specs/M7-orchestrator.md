# M7 · 编排器 + 遍历器 Spec

> 依据契约 `docs/contract.md` §5.7（行为树确定性编排）、§5.7.2（叶子触发）、§5.7.7（行为树遍历器语义 tick）、§5.4（控制流）、§5.9（会话生命周期初始化）、§12.4（可查询执行状态）。
>
> **实现状态：已实现 ✅**（OpenSpec change `m7-orchestrator`，2026-08）。代码位于 `webops/orchestrator/`，测试位于 `tests/orchestrator/`（含 `tests/orchestrator_helpers.py` 共享 mock 构造器）。本文件已与实现同步；涉及契约语义的实现细节见「与契约的接口细节」一节，供统一更新 `docs/contract.md`。

## 1. 概述

确定性编排器：遍历内部行为树（M2 产出），纯程序执行组合节点，触发叶子节点执行（M6），维护 schema 帧（M3）与记录报告（M8）。提供 `engine.run(行为树)` 入口并维护**可查询的执行状态**供 M9b 轮询。**依赖 M2 + M3 + M6 + M8，是引擎的整合中枢。**

## 2. 功能范围

| 功能 | 说明 | 契约依据 | 实现 |
|---|---|---|---|
| 行为树遍历 | 阻塞式遍历，SUCCESS/FAILURE 聚合，组合节点短路 | §5.7.7 | ✅ `Traverser.tick`（递归，design D1） |
| 组合节点执行 | Sequence/Selector/Repeat 纯程序遍历，零 LLM | §5.7.7 | ✅ `_tick_sequence/selector/repeat` |
| 叶子节点触发 | 触发 M6 agent 执行，接收结果 | §5.7.2 | ✅ `_tick_leaf`（经注入的叶子执行器） |
| 失败传播 | 叶子失败沿树传播，根统一终止 + 报告 | §5.7.7/§5.7.2.1 | ✅ 组合节点聚合 + `RunResult.failure_reason` |
| schema 帧管理 | 每次块引用建立/释放 schema 帧（M3） | §5.7.4 | ✅ `_sync_frame`（enter_block/exit_block） |
| 会话初始化 | 创建全新浏览器 context，注入全局默认配置到根级 schema | §5.9/§9.8 | ✅ `Engine.run` 开头/结尾 |
| 执行状态维护 | 当前进度/当前节点/已完成节点报告（供 M9b 轮询） | §12.4 | ✅ 复用 M8 `ExecState`（`Reporter.exec_state`） |
| 超时 | 全局 timeout 在节点层面生效 | §5.7.7 | ✅ 协作式 deadline 下传 + wall-clock 兜底（design D6） |

## 3. 数据依赖

### 3.1 输入
- **内部行为树对象 + 块声明**（来自 M2）：`BehaviorTree` / `ActionNode` / `ConditionNode` / `SequenceNode` / `SelectorNode` / `RepeatNode` / `FinishNode` / `BlockDecl`
- **schema 命名空间**（来自 M3）：帧管理（`enter_block`/`exit_block`）、配置继承（`resolve_config`）、页面变量（`current_page`）
- **叶子执行**（来自 M6）：`execute_leaf(node, ctx)` → `LeafResult`（经 `RunConfig` 注入 M0/M5 依赖或注入 mock）
- **报告**（来自 M8）：`Reporter.start_node/record_node/capture_screenshot/exec_state/finalize`

### 3.2 输出
- **运行结果**：`RunResult`（成功/失败 + 终止原因 + 两份报告）
- **可查询执行状态**：`ExecState`（进度/当前节点/已完成报告，供 M9b）
- **浏览器会话生命周期管理**：M1 `BrowserDriver.start`（冷启动）/`stop`（统一释放）

## 4. 单元间依赖

- **依赖**：
  - M2（行为树解析器）— 内部行为树对象
  - M3（schema 命名空间）— 帧管理
  - M6（叶子 agent 执行）— 叶子结果
  - M8（报告机制）— 报告记录
- **被依赖**：
  - M9b（后端）— `engine.run()`、执行状态查询

## 5. 接口契约（已实现）

### 5.1 引擎入口（已实现）

```python
class Engine:
    def run(self, tree: BehaviorTree, blocks: dict[str, BlockDecl],
            config: RunConfig) -> RunResult: ...
    def get_exec_state(self) -> ExecState: ...   # 供 M9b 轮询

@dataclass(frozen=True)
class RunResult:
    status: Literal["success", "failure"]
    failure_reason: str | None = None
    exec_report: ExecReport | None = None    # 校验失败不启动遍历时为 None
    trace_report: TraceReport | None = None
```

**`Engine` 构造注入（design D2/D7，mock 友好）：**

```python
Engine(
    *,
    browser: BrowserDriver | None = None,        # 默认新建实例
    leaf_executor: Callable[[Node, float | None], LeafResult] | None = None,
    space_factory: Callable[[], SchemaSpace] | None = None,   # 默认每次新建
    reporter_factory: Callable[[str, int], Reporter] | None = None,  # 默认 M8
)
```

**`RunConfig`（运行配置）：**

```python
@dataclass(frozen=True)
class RunConfig:
    timeout: float | None = 120.0      # 全局叶子超时（注入根级 schema "timeout"）
    max_rounds: int = 10               # 叶子 LLM 工具调用轮数上限（传 M6）
    no_progress_rounds: int = 2        # 连续无进展阈值（传 M6）
    session_timeout: float = 60.0      # 单次 LLM 请求超时（传 M6）
    initial_graph_scope: str = "full"  # 初始语义图范围（传 M6）
    initial_graph_lod: int = 2         # 初始语义图 LOD（传 M6）
    report_dir: str = "reports"        # 报告持久化根目录（M8）
    browser_config: BrowserConfig | None = None
    global_config: dict[str, Value] = {}   # 额外全局默认配置（注入根级 schema）
    llm_config: LLMConfig | None = None    # 真实叶子执行需要（M0）
    engine: EngineFunctions | None = None  # 真实叶子执行需要（M5）
    session_factory / tools: ...           # 传 M6（可选）
```

**真实叶子执行的接线说明**：`run` 默认经 `make_default_leaf_executor(config)` 构造
`LeafContext`（含生效 timeout）并调用 M6 `execute_leaf`；需要 `config.llm_config`
与 `config.engine`（M0+M5）同时注入，否则抛出 `OrchestratorError`。测试全部注入
mock 叶子执行器（`(node, timeout) -> LeafResult`），不依赖 M0/M5/M6 真实实现。

**入口校验**（§5.1 场景「校验失败不启动遍历」）：行为树/块声明/配置缺失或配置类型
非法 → 直接返回 `RunResult(status="failure", failure_reason=...)`，不创建会话、
不遍历、不产出报告（`exec_report`/`trace_report` 为 None）。

### 5.2 可查询执行状态（§12.4，已实现）

复用 M8 `ExecState`（单数据源，design D3）：`run_id` / `progress`（派生
`completed/total_nodes`）/ `current_node` / `completed` / `finished`。
`Engine.get_exec_state()` 直接返回 `Reporter.exec_state()` 快照（副本，读侧安全）；
未运行返回 `ExecState(run_id="")`。节点进入 `start_node` 写 `current_node`、退出
`record_node` 追加 `completed` 并推进 `progress`，全部节点结束 `finalize` 置
`finished=True`。

### 5.3 遍历器语义（§5.7.7，已实现）

- **阻塞式**：一个节点执行完才执行下一个；节点状态只有 SUCCESS/FAILURE，无 RUNNING
- **Sequence**：依次执行，第一个 FAILURE 短路 → 整体 FAILURE；全 SUCCESS → SUCCESS
- **Selector**：按条件分流，分支条件先判（FAILURE 试下一分支），命中分支的子节点
  结果即 Selector 结果并短路；全分支条件 FAILURE → FAILURE（不承载兜底，命中后
  子节点失败不回落下一分支）
- **Repeat**：循环带上限（`max`），到达上限 → 整体 FAILURE
  - **LoopUntil**：每轮先判 until（页面条件），满足即退；不满足才执行 body；
    body 失败 → 整体 FAILURE（失败沿树传播，不吞掉继续循环）
  - **Retry**：每轮直接执行 body，成功即退；失败重试至上限
- **失败传播**：叶子 FAILURE 沿树向上由组合节点聚合，根统一终止 + 报告
- **超时**：全局 timeout 在节点层面生效（§5.7.2.1 终止条件③）——生效值经
  `resolve_config('timeout')`（自身 → 祖先 → 全局默认）取块覆盖/全局默认，
  折算为 deadline 传入叶子执行器，返回后 wall-clock 兜底判定超时置 FAILURE

### 5.4 运行初始化（§9.8 ⓪/①，已实现）

1. 入口校验（树/块/配置）
2. 创建全新浏览器 context（M1 `start`，从 0 开始，无持久化）
3. 注入全局默认配置到根级 schema（`timeout` + `global_config`）
4. 建立根级块帧（`enter_block(tree.name)`）
5. 遍历执行
6. 遍历结束（无论成败）统一 `browser.stop()` 释放会话

## 6. 验收标准（全部已实现并通过测试 ✅）

- [x] 阻塞式遍历正确，节点状态聚合与短路符合 §5.7.7
- [x] 组合节点纯程序执行，零 LLM
- [x] Repeat 的 LoopUntil/Retry 两种模式行为正确（先判/后判），上限触发 FAILURE
- [x] 叶子失败正确沿树传播，根终止
- [x] 每次块引用建立独立 schema 帧，运行结束释放
- [x] 会话初始化：全新 context + 全局配置注入根级 schema
- [x] 执行状态可查询：进度/当前节点/已完成报告正确更新
- [x] 全局超时生效
- [x] mock 叶子执行下可完整测试遍历/聚合/传播逻辑

## 7. 测试策略（已实现，测试位于 `tests/orchestrator/`）

| 测试文件 | 覆盖任务 |
|---|---|
| `test_models.py` | 1.1 状态常量/RunConfig/RunResult；1.2 RunContext 依赖注入与 schema_decl 转换 |
| `test_traverser.py` | 1.3 tick 契约（阻塞式、状态映射、报告记录） |
| `test_composites.py` | 2.1~2.6 Sequence/Selector/Repeat（两模式）表驱动矩阵、上界、短路、节点报告 |
| `test_leaf_timeout.py` | 3.1 叶子触发与布尔映射；3.2 LeafTrace 随报告；3.3 失败传播；3.4 全局超时；3.5 超时继承 |
| `test_schema_frames.py` | 4.1 建帧/释放/隔离（含嵌套与失败释放）；4.2 三级配置继承 |
| `test_session.py` | 4.3 每次 run 全新 context；4.4 全局配置注入根级 schema；4.5 会话释放 |
| `test_exec_state.py` | 5.1~5.4 进度单调推进、current_node 时序、快照副本、finished |
| `test_engine_integration.py` | 1.4 入口（含校验失败不启动遍历）；6.1 mock 树端到端聚合；6.2 真实浏览器冒烟（`@pytest.mark.integration`） |

- **mock 策略**：mock M6 为 `StubLeaf`（按描述返回固定 `LeafResult`，可脚本化序列）
  / `BlockingLeaf`（慢执行测超时），mock M1 为 `MockBrowser`（记录 start/stop）；
  **不依赖 M9a/M9b**，组合节点逻辑零 LLM。
- 测试数：78 个（`tests/orchestrator/`），全部经 `webops` conda 环境 `pytest` 通过；
  全库 636 passed, 3 skipped；`ruff check .` 无告警。
- 集成冒烟（6.2）：真实 `BrowserDriver` + data: URL 页面 + mock 叶子，验证
  页面变量写入、截图落盘与报告链路在真实环境下工作。

## 8. 与契约的接口细节（待统一更新 contract.md）

1. **入口校验失败不产出报告**：`engine.run` 在行为树/块声明/配置缺失或类型非法时
   直接返回 `RunResult(status="failure", failure_reason=...)`，`exec_report` /
   `trace_report` 为 None，不启动会话/遍历（§5.1 场景）。**建议 contract §5.1 标注
   `RunResult` 两份报告在校验失败路径下为可选（None）。**
2. **叶子执行器注入形态**：M7 的叶子执行器签名为 `(node, timeout) -> LeafResult`，
   默认经 `RunConfig` 构建 M6 `LeafContext` 后调用 `execute_leaf`（需注入
   `llm_config` + `engine`）；测试/mock 直接注入 `(node, timeout)` 可调用对象。
   **建议 contract §5.7.2 标注 M7 通过注入点触发 M6，M0/M5 依赖由调用方接线。**
3. **超时语义**：生效 timeout 经 `resolve_config('timeout')`（自身 → 祖先 → 全局
   默认）解析；协作式 deadline 下传 M6（`LeafContext.timeout`），遍历器返回后再做
   wall-clock 兜底判定（超时置 FAILURE）。**建议 contract §5.7.7 明确「块覆盖
   timeout 时该块及子树叶子用覆盖值」。**
4. **LoopUntil body 失败语义明确化**：每轮先判 until 满足即退；**body 失败 → 整体
   FAILURE 立即传播**（不吞掉失败继续循环）。**建议 contract §5.7.7 补充该句。**
5. **Selector 命中分支后子节点失败 → 整体 FAILURE（不回落下一分支）**：分支条件
   命中即「提交」，子节点结果即 Selector 结果（§5.7.7「不承载兜底」的落地）。
   **建议 contract §5.7.7 明确命中后失败不回落。**
6. **schema 帧同步方式**：M7 经 `SchemaSpace._current`（内部当前帧指针）与节点
   `frame` 字段做 LIFO 建帧/释放同步（M3 无公开「当前帧」读取器）。`resolve_config`
   继承链 + `enter_block` 注入块配置覆盖，天然实现「自身 → 祖先 → 全局默认」。
7. **ExecState 复用 M8**：M7 不新增执行状态模型，直接经 `Reporter.exec_state()`
   复用 M8 `ExecState`（§12.4 数据源单一，进度由 completed/total_nodes 派生）。
8. **真实叶子执行的依赖边界**：M7 不构造 M0/M5；真实执行需要调用方在 `RunConfig`
   注入 `llm_config` + `engine`（或自定义 `leaf_executor`）。**建议 contract §12.3
   标注 M9b 接线 M0+M5+M6 后注入 M7。**