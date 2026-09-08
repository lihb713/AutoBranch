# M4 · 语义图生成 Spec

> 依据契约 `docs/contract.md` §7（语义图内容模型）、§8（语义图生成）、§8.3（两阶段流水线）、§8.4（候选元素筛选）、§8.8（语义图接口）、§9.5（LOD 分级）。
>
> **实现状态：已实现 ✅**（OpenSpec change `m4-semantic-graph`，2026-08）。代码位于 `webops/semantic_graph/`，测试位于 `tests/semantic_graph/`（含 `tests/snapshot_factory.py` 快照构造器与 `tests/fixtures/sg_login.html`/`sg_orders.html` 页面 fixture）。本文件已与实现同步；涉及契约语义的实现细节见「与契约的接口细节」一节，供统一更新 `docs/contract.md`。

## 1. 概述

将原始 DOM 页面加工为**语义图**（§7.5 结构化对象模型），供 LLM 理解页面。采用**两阶段流水线**：程序化阶段（DOM 爬取 + 结构 + 几何 + 程序化值）+ LLM 填充阶段（purpose + related-to 打分），并提供 LOD 分级的 `semantic_graph(范围, LOD)` 统一接口与 LLM 可读的序列化文本。**依赖 M1（DOM 爬取）+ M0（LLM 填充）。**

## 2. 功能范围

| 功能 | 说明 | 契约依据 | 状态 |
|---|---|---|---|
| 候选元素筛选 | 可交互 + 携带文本必进、语义容器作层级骨架、纯结构归属性、过滤隐藏 | §8.4 | ✅ `selection.py` |
| 程序化阶段 | DOM 爬取、role/层级/part-of、bounds/可见性/阅读顺序、程序化值 | §8.3 | ✅ `programmatic.py` 编排 |
| LLM 填充阶段 | 每个元素 purpose、related-to 关联打分与理由 | §8.5/§8.6/§8.7 | ✅ `llm_fill.py` |
| 语义图接口 | `semantic_graph(范围, LOD)`，每次完整生成，无缓存 | §8.8/§9.5 | ✅ `interface.py` |
| 序列化 | 引擎对象模型 → LLM 层次树文本 | §7.6 | ✅ `serialize.py` |
| LOD 分级 | 四维参数（深度/广度/属性/关联）组合 LOD-0~3 | §9.5 | ✅ `lod.py` |
| token 预算 | 序列化估算超限可检测（不静默截断） | §8.8 ⑤/§9.5 | ✅ `budget.py` |
| ref 映射表 | `[N]` ↔ 元素 id ↔ DOM 节点双向解析（策略 B 即用即弃） | §7.8 | ✅ `refs.py` |

**非目标（第一版）**：不处理 iframe、懒加载/虚拟滚动/动态渲染、Canvas 渲染页面（依赖 M1 爬取边界）；不做缓存/指纹/失效机制；不做跨快照身份跟踪与稳定 ref。

## 3. 数据依赖

### 3.1 输入
- **DOM 快照**（来自 M1 `DomProbe.crawl`，可 mock）：节点树、role、可见性、bounds、程序化值
- **LLM 会话**（来自 M0 `LLMSession`，可 mock）：填充 purpose 与 related-to 打分
- **参数**：`范围`（`full` / 区域 id，如 `F1`/`T1`）、`LOD`（0~3 或 `LODSpec`）

### 3.2 输出
- **语义图对象模型**（§7.5）：图根 + 区域节点 + 元素节点 + 边 + 可选 changes（默认空）+ `ref_map`（引擎侧映射表）
- **序列化文本**：LLM 视角的层次树（§7.6）

## 4. 单元间依赖

- **依赖**：
  - M1（浏览器驱动）— DOM 爬取、元素状态读取（`DomSnapshot`/`ElementNode`/`LODSpec`）
  - M0（LLM 客户端）— LLM 填充阶段（`LLMSession`，`estimate_tokens` 用于预算估算）
- **被依赖**：
  - M5（引擎函数层）— 提供 `semantic_graph` 引擎函数给 LLM（注入 `DomProbe` 与 `LlmFiller`）

## 5. 接口契约（已实现）

### 5.1 语义图接口

```python
def semantic_graph(
    page_ref: PageRef,
    scope: str = "full",          # full / 区域 id（如 "F1"、"T1"）
    lod: int | LODSpec = 2,       # LOD-0~3 或 LODSpec
    probe: DomProbe | None = None,      # M1 爬取探针（调用方注入，如 M5）
    filler: LlmFiller | None = None,    # LLM 填充器（调用方注入）
    budget_limit: int | None = None,    # token 预算上限（None 不检测）
) -> SemanticGraph
```

- 每次调用完整执行程序化阶段 + LLM 填充阶段，**无缓存、无指纹、无失效机制**（§9.5）。
- 范围控制广度维度；LOD 控制精细程度；程序化值（如 input 当前值）每次实时读取。
- 失败分类：`ProgramStageError`（程序侧，可重试）、`LlmStageError`（LLM 侧，重试无意义）、`SemanticGraphBudgetExceeded`（超限，不静默截断）。

### 5.2 语义图结构（§7.5）

```python
@dataclass
class SemanticGraph:
    type: str = "semantic-graph"
    version: str = "0.1"
    page: PageInfo                    # url, title, page_type
    regions: list[Region]
    elements: list[Element]
    edges: list[Edge]
    changes: list[Change] = []
    ref_map: RefMap                   # 引擎侧确定性 ref 映射表（§7.8）
```

### 5.3 区域/元素/边

- **Region**：id、ref（如 `[F1]`）、region_type、label（LLM 填充）、bounds、child_elements、depth（语义容器嵌套层数）
- **Element**：id、ref、role、purpose（LLM 填充）、state（value/checked/disabled/visible/text/selected，程序化）、options、bounds、confidence、dom_node_id（ref 映射到 DOM 节点）
- **Edge**：type（related-to/part-of/value-of）、from/to、origin（visual/structural）、confidence、score、reason、detail

### 5.4 LOD 分级（§9.5）

| LOD | 深度 | 广度 | 属性 | 关联 | 用途 |
|---|---|---|---|---|---|
| 0 | 0 | 只含候选 | 仅 role+名 | 无 | 页面概览 |
| 1 | 1 | 区域 | 含 value | 高分边（score≥0.7） | 正常定位 |
| 2 | 2 | 整区域 | 含相关文本 | 全部分数+理由 | 复杂判断/提取 |
| 3 | 全部 | 全部 | 全部 | 全部 | 疑难兜底 |

- 深度/广度在 LLM 填充**之前**裁剪（控制纳入候选集合的元素数量，节省 LLM 输入）；属性/关联在 LLM 填充**之后**作用于最终输出（design D4）。
- part-of/value-of 结构边始终保留（关联维度只裁剪 related-to）。

### 5.5 序列化（§7.6）

- 区域 → `REGION <type> <ref> <label>`
- 元素 → `<缩进> <role前缀> [<ref>] <purpose> [状态]`，related-to 括号标注
- 文本承载元素 → `<缩进> <role> [<ref>] <purpose>="<text>"`
- part-of 编码为缩进层级，兄弟按视觉顺序排列；value-of 以单元格并列（`CELL [N] 字段="值"`）呈现
- id/bounds 不进文本，confidence 仅歧义时标注

### 5.6 每次完整生成（无缓存）

每次调用都跑程序化阶段 + LLM 填充，保证语义图始终正确反映当前页面（§9.5）。token 预算控制：LOD + 范围 + `budget_limit`（超限抛 `SemanticGraphBudgetExceeded`）。

## 6. 验收标准（全部已实现并通过测试 ✅）

- [x] 程序化阶段：DOM 快照 → 候选元素/区域/边（part-of/value-of）正确，过滤隐藏元素
- [x] LLM 填充阶段（可 mock）：purpose 与 related-to 打分被填充进元素与边
- [x] `semantic_graph(范围, LOD)` 返回完整语义图
- [x] LOD 各级输出符合维度定义（深度/广度/属性/关联）
- [x] 序列化文本符合 §7.6 格式，ref 映射表正确（§7.8）
- [x] 每次调用完整生成，输入变化反映到输出
- [x] token 预算超限可检测
- [x] 程序化阶段可独立测试（不依赖 LLM）

## 7. 测试策略（`tests/semantic_graph/`）

- **程序化阶段独立测试**：固定 HTML fixture（`tests/fixtures/sg_login.html`/`sg_orders.html`）+ 纯构造 `DomSnapshot` 的快照构造器（`tests/snapshot_factory.py`）→ 断言候选集/区域/边/bounds
- **LLM 填充 mock 测试**：`MockFiller`（按 `dom_node_id` 键控）返回固定 purpose/打分 → 断言写入正确；`LLMSessionFiller` 走 M0 `LLMSession` + `tests/fake_transport.py` 驱动（不改动 M0 测试文件）
- **LOD 测试**：同一页面四档 LOD 输出符合维度定义
- **序列化快照测试**：语义图 → 期望文本（登录页/订单列表快照）
- **空间方位测试**：带 `viewport` 的语义图元素/区域行尾输出九宫格方位词（如 `(页面top-right)`）；无 viewport 不输出；方位计算按中心点相对视口（`test_geometry_quadrant.py` / `test_serialize_quadrant.py`）
- **ref 映射测试**：`[N]` ↔ 元素 id ↔ DOM 节点双向解析
- **预算测试**：构造超预算场景断言 `SemanticGraphBudgetExceeded` 触发
- **集成测试**（`pytest -m integration`）：真实浏览器 + mock LLM，从真实页面生成语义图并断言对象模型与序列化文本；输入值变化反映到下次调用
- **集成冒烟**（`pytest -m smoke`，可选）：真实 M0 LLM，需 `WEB_OPS_TEST_LLM=1` 与环境配置，人工检查 purpose/related-to 合理性
- **独立性**：程序化子模块不 import `webops.llm`；M1 快照可 mock，测试不依赖 M5/M6/M7

## 8. 与契约的接口细节（待统一更新 contract.md）

1. **`semantic_graph` 签名含注入依赖**：契约 §8.8 写作 `semantic_graph(范围, LOD)`，实现为 `semantic_graph(page_ref, scope, lod, probe, filler, budget_limit)`——`probe`（M1 `DomProbe`）与 `filler`（`LlmFiller`）由调用方（M5 引擎函数层）注入，未注入时报对应阶段错误。
2. **LOD 深度与广度裁剪**：LOD-0 深度=0 同时裁剪掉深度>0 的嵌套容器及其元素；广度 `direct`=只含容器层级 0 的元素、`region`=深度内全部、`full`=全部。
3. **属性维度定义**：`minimal`=仅 role+purpose（文本承载元素保留 text 作为内容）；`standard`=+value/checked/disabled/selected；`rich`=+options 与全量文本；`full`=全部。
4. **相关边打分约束**：LLM 的 related-to 打分只接受几何候选集内的关联（候选预筛为输入边界，§8.5），非候选打分被丢弃。
5. **区域 id/ref 规则**：区域 id 与 ref 去括号一致（form→`F1`/`[F1]`、table→`T1`、row→`R1`、rowgroup→`G1`、list→`L1`、nav→`N1`、section→`S1`、dialog→`D1`、fieldset→`GS1`）；元素 id 为 `E1`..，ref 为 `[1]`..（按阅读顺序）。范围参数匹配区域 id 或 ref（去括号）。
6. **失败语义**：`semantic_graph` 中 DOM 爬取失败（`PageRefError`）包装为 `ProgramStageError`（可重试）；`FatalBrowserError` 保持传播（致命）；LLM 填充失败（含 M0 连接/解析异常）包装为 `LlmStageError`（M4 语义图填充层面统一按 LLM 侧失败报告，连接类错误的重试分流由上层 M6/M7 按 §9.4 处理）。
7. **LLM 填充器接口**（design D1）：`LlmFiller.fill_purpose(elements, regions) -> PurposeResult`（元素 purpose + 区域 label）+ `score_related_to(candidates) -> list[RelatedScore]`；真实实现 `LLMSessionFiller` 每次填充发一次请求、要求 JSON 返回、ref 由引擎分配模型只原样引用。
8. **每次完整生成（无缓存）**：`semantic_graph` 每次调用都会重新 `DomProbe.crawl`（全量 LOD-3 深度）+ 完整两阶段，不做任何缓存/指纹（与 §9.5 一致，无契约变更，仅确认实现）。
9. **超预算不静默截断**：预算超限抛 `SemanticGraphBudgetExceeded`（可降级重试：降低 LOD 或缩小范围），不返回截断语义图。
10. **空间方位标注**：M1 快照携带 `viewport`（视口尺寸，JS 注入 `window.innerWidth/Height`）；`geometry.page_quadrant(bounds, viewport)` 按元素中心相对视口计算九宫格方位词（`top`/`middle`/`bottom` × `left`/`center`/`right`）；`serialize` 在元素/区域行尾输出 `(页面<方位>)`。方位是稳定空间语义（非像素），页面小幅滚动不影响词面；无 viewport 时不输出。供 LLM 理解「右上角/第5行右侧」等位置指令。