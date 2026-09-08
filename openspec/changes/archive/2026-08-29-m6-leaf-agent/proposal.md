## Why

WebOps 的核心设计是"流程流转确定、LLM 只在叶子节点内行使有界执行权"（契约 §5.7.2），但目前尚无可执行的叶子 agent 层：Action/Condition 叶子节点的执行、引擎与 LLM 的边界（§5.7.2.1）、多轮定位（§9.6）、终止兜底（§9.7）与错误分流（§9.4）都只停留在契约层面。M6 是实现这一设计的执行核心——没有它，行为树无法在真实页面上落地操作与判断，M7 编排器与 M9b 后端也无从整合。

## What Changes

- 新增 `leaf-agent` capability：实现 Action / Condition 叶子节点的 agent 式执行——将节点自然语言描述 + 当前语义图交给 LLM，由 LLM 自主决定调用 M5 引擎函数，引擎只做兜底。
- Action 执行：LLM 结合描述与语义图自主调用引擎函数（click/type/select/...），最终返回 `Success | Failure` 作为叶子节点状态。
- Condition 执行：LLM 自主判断条件是否满足，返回确定的布尔值作为节点状态依据（§5.5），推理期间引擎不介入。
- 多轮定位：LLM 可多次调用 `semantic_graph(范围, LOD)` 缩小/放大搜索目标元素（§9.6），搜索控制权完全归 LLM。
- 引擎兜底终止条件（§5.7.2.1）：LLM 对话轮数上限 / 连续 N 轮无进展 / 单叶子执行超时，任一触发即终止叶子并记为 LLM 侧失败，沿行为树传播。
- 错误边界（§5.7.2.1/§9.4）：函数失败以工具调用结果回传 LLM 由其自行修正（agent 语义）；程序侧致命错误（浏览器崩溃/网络断开）直接终止整个流程。
- 错误分类：按错误源（LLM 侧 vs 程序侧）分流记录，供 M8 报告回溯。
- 契约落码：提供 `execute_leaf` 接口及 `LeafResult` / `LeafTrace` 数据结构，输出推理过程与工具调用序列供 M8 回溯报告。
- 提示词设计：封装"节点描述 + 语义图 → 可靠决策"的系统提示词，与 LLM 会话（M0）的 agent 多轮工具调用集成。

## Capabilities

### New Capabilities
- `leaf-agent`: Action/Condition 叶子节点的 agent 式执行能力，涵盖 LLM 自主调用引擎函数、多轮定位、引擎兜底终止条件、错误边界与错误分类，以及执行追踪数据契约。

### Modified Capabilities
<!-- 无：openspec/specs 尚无既有 capability，本 change 不修改任何既有 spec -->

## Impact

- **新增代码**：M6 叶子 agent 执行模块（调用 M0 LLM 会话 + M5 引擎函数集）。
- **依赖**：M0（LLM 客户端，agent 多轮工具调用会话）、M5（引擎函数层：操作函数 + semantic_graph + OpResult 错误语义）。
- **被依赖**：M7（编排器）通过 `execute_leaf` 触发叶子执行并获取 `LeafResult`；M8（报告机制）读取 `LeafTrace` 执行追踪数据。
- **API**：对外契约 `execute_leaf(node, ctx) -> LeafResult`，数据结构 `LeafResult` / `LeafTrace` / `ToolCallRecord`。
- **错误语义**：LLM 侧失败（定位/理解/判断失败）与程序侧失败（浏览器崩溃/网络超时）两类，处理方式不同，需与 M8 报告分流对齐。