> **模块重编号**：原 **M8 报告机制** 重编号为 **M6**。报告为引擎基础 + 插件附加（插件驱动）。

# M8 · 报告机制 Spec

> 依据契约 `docs/contract.md` §5.8.3（报告机制）、§5.7.2.1（LLM 推理记录）、§12.4（可查询执行状态）。

> **实现状态**：✅ 已实现（`autobranch/reporting/`，独立模块，未接入 M7 遍历器）。
> 实现细节与测试覆盖见文末「8. 实现说明」。

## 1. 概述

记录行为树执行过程的**两份报告**：执行情况报告（每节点结果 + 截图）与回溯报告（执行详情 + LLM 推理，不含截图）。所有节点退出前记录执行情况，Action/Condition 返回前额外截图。**依赖 M1（截图）+ 可查询的执行状态。**

## 2. 功能范围

| 功能 | 说明 | 契约依据 |
|---|---|---|
| 节点报告记录 | 所有节点退出前记录执行情况 | §5.8.3 |
| 截图 | Action/Condition 节点返回前截图 | §5.8.3 |
| 执行报告 | 每节点结果 + 截图 | §5.8.3 |
| 回溯报告 | 执行详情 + LLM 推理（不含截图） | §5.8.3 |
| 执行状态查询 | 进度/当前节点/已完成报告（供 M9b 轮询） | §12.4 |
| 报告存储 | 截图/报告文件持久化（供 M9b 提供） | §12.4 |

## 3. 数据依赖

### 3.1 输入
- **节点执行数据**（来自 M7/叶子执行）：节点类型/描述/结果/时间/URL
- **Action 调用记录**：调用的引擎函数、是否成功
- **Condition 判断结果**：布尔值
- **LLM 推理数据**（来自 M6 LeafTrace）：输入/推理过程/决策结果
- **截图**（来自 M1）：Action/Condition 的页面状态

### 3.2 输出
- **执行报告**（含截图）
- **回溯报告**（含 LLM 推理，不含截图）
- **可查询执行状态**：供 M9b 前端轮询

## 4. 单元间依赖

- **依赖**：
  - M1（浏览器驱动）— 截图能力
  - M7（编排器）— 节点执行数据流（M8 被 M7 调用记录）
  - M6（叶子 agent）— LLM 推理追踪数据
- **被依赖**：
  - M7（编排器）— 记录报告
  - M9b（后端）— 提供报告/执行状态给前端

## 5. 接口契约

### 5.1 报告记录接口（被 M7 调用）

```python
class Reporter:
    def record_node(self, node_report: NodeReport) -> None: ...
    def capture_screenshot(self, page_ref: PageRef, desc: str | None = None) -> str: ...  # 返回路径
    def finalize(self) -> ReportBundle: ...

@dataclass
class NodeReport:
    node_type: str                  # Action/Condition/Sequence/...
    node_desc: str
    result: Literal["success", "failure"]
    action_call: ActionCall | None  # Action 专有
    condition_result: bool | None   # Condition 专有
    timestamp: str
    page_url: str | None
    screenshot_path: str | None     # Action/Condition 专有
    llm_trace: LeafTrace | None     # 回溯报告专用
```

**实现细节（已落地）**：

- `Reporter(run_id, report_dir, screenshotter=None, total_nodes=None)`：
  - `screenshotter`：包装 M1 `PageHandle.screenshot` 的回调 `(page_ref, path) -> OpResult`
    （产物在 `detail["path"]`）；不注入则截图被跳过（返回空串）。这是 M8 对 M1
    的单方向、可 mock 依赖（设计决策 1/4）。
  - `total_nodes`：树中节点总数（执行前由 M2 解析产物可知），供 `progress` 计算。
- `start_node(node_info: NodeInfo)`：**扩展接口**——M7 在节点开始执行前调用，
  更新 `ExecState.current_node`（§12.4「当前执行节点」的追踪来源）。
- `capture_screenshot(page_ref, desc=None)`：`desc` 为可选描述，用于生成可读截图
  文件名（`<序号>_<描述>.png`，存储于 `<report_dir>/<run_id>/`）。
- `exec_state() -> ExecState`：执行状态查询快照，`completed` 返回副本，查询不改变执行。
- `ExecState.progress` 为**派生属性**（决策 3 单数据源）：`已完成节点数 / total_nodes`，
  非存储字段；`finished` 后恒为 1.0。

### 5.2 两份报告（§5.8.3）

```
报告① 执行情况报告 (每节点结果 + 截图):
  每个节点: 节点类型/描述/结果/函数调用/判断结果/时间/URL/截图
  用途: 概览流程执行结果

报告② 回溯报告 (执行详情 + LLM 推理, 不含截图):
  每个节点: 执行情况 + LLM 输入/推理过程/决策结果
  用途: 深挖问题回溯
```

### 5.3 执行状态查询（§12.4）

```python
@dataclass
class ExecState:
    run_id: str
    current_node: NodeInfo | None
    completed: list[NodeReport]
    finished: bool
    total_nodes: int | None         # progress 计算依据（决策 3 单数据源）

    @property
    def progress(self) -> float: ...  # 0.0 ~ 1.0，派生属性
```

> 说明：`progress` 以派生属性实现（非存储字段），保证轮询与最终报告始终一致
> （单数据源）；存储时额外持有 `total_nodes` 供进度计算。

## 6. 验收标准

- [x] 所有节点退出前都记录执行情况
- [x] Action/Condition 返回前截图并关联到节点报告
- [x] 执行报告包含每节点结果 + 截图
- [x] 回溯报告包含 LLM 推理过程，且不含截图
- [x] 两份报告生成正确、格式清晰
- [x] 执行状态可查询：进度/当前节点/已完成报告正确
- [x] 截图/报告持久化，路径可被 M9b 提供

## 7. 测试策略

- **mock 节点执行数据测试**：构造节点报告 → 验证两份报告生成（`tests/reporting/test_reports.py`）
- **截图测试**：mock M1 截图 → 验证关联路径（`tests/reporting/test_screenshot.py`）
- **LLM 推理测试**：mock LeafTrace → 验证回溯报告内容（`tests/reporting/test_reports.py`）
- **执行状态测试**：节点完成 → 状态累积/进度更新正确（`tests/reporting/test_reporter.py`）
- **独立性**：mock M1/M6/M7 数据，不依赖浏览器/LLM 真实执行（`tests/reporting/test_independence.py`）；
  真实截图用例打 `pytest.mark.integration`（`tests/reporting/test_reporting_integration.py`）

## 8. 实现说明

**代码位置**：

| 文件 | 内容 |
|---|---|
| `autobranch/reporting/models.py` | `NodeReport`/`ActionCall`/`ToolCallRecord`/`LeafTrace`/`NodeInfo`/`ExecState`/`ExecReport`/`TraceReport`/`ReportBundle`（dataclass，风格对齐 M1 `models.py`） |
| `autobranch/reporting/render.py` | 执行报告（报告①）与回溯报告（报告②）文本渲染 |
| `autobranch/reporting/reporter.py` | `Reporter`：`record_node`/`start_node`/`capture_screenshot`/`exec_state`/`finalize` |

**数据契约（本 change 内定义，不依赖 M6 实现）**：

- `ActionCall`：`function`/`success`/`arguments`/`error`。
- `LeafTrace`：`llm_input`（节点描述 + 语义图）/`llm_reasoning`（推理过程）/
  `decision`（决策结果）/`calls`（工具调用序列，`ToolCallRecord`）/`terminator`（终止条件）。
  M6 实现时需与此契约对齐。

**存储布局**（决策 5）：`<report_dir>/<run_id>/` 下存放 `NNN_<desc>.png` 截图、
`exec_report.md`（报告①）、`trace_report.md`（报告②）；run_id 经清洗为安全目录名。

**截图引用格式**：执行报告（报告①）的截图以 **Markdown 图片语法** 输出
（`![节点截图: <节点描述>](<相对文件名>)`）。截图与 `exec_report.md` 同目录，
故用相对文件名即可在 Markdown 预览中直接显示图片（alt 文本用清洗后的节点描述）。

**契约语义说明（供 contract.md 统一更新）**：见任务汇报——新增 `start_node` 钩子、
`ExecState.progress` 派生属性、`Reporter` 构造参数（screenshotter/total_nodes）等。


## 8. 插件驱动报告（能力插件化新增，已实现）

报告 = **引擎基础字段**（node_type / desc / result / timestamp / action_call / llm_trace）+ **插件附加信息**（`FunctionResult.report`，引擎落笔，按来源分组展示）。

引擎**不硬编码能力专属字段**（如 page_url / screenshot）；截图由浏览器插件在 `semantic_graph`（"看页面"）时产出，经 `LeafResult.screenshots` 写入 `NodeReport.screenshot_path`（非浏览器操作不产生截图）。
