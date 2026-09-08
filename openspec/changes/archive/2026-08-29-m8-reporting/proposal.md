## Why

WebOps 引擎当前只确定性地遍历行为树、在叶子节点内执行 LLM 代理，但**不记录执行过程**：没有节点级执行情况、没有页面截图、也没有可查询的执行状态。管理系统（M9b）需要向用户实时展示执行进度与每步结果（§12.4 轮询），而用户需要能回溯"为什么某步失败 / LLM 为什么这么做"。缺少报告机制，执行过程对用户完全不可见，前端执行报告页、截图展示、回溯排查均无从谈起。因此必须在 M7 编排器整合前补齐 M8 报告机制（阶段 2 模块）。

## What Changes

- 新增 **`reporting`** capability：实现报告记录与生成，作为 M7 整合前的独立模块。
- **节点报告记录**：所有节点（整棵行为树）退出前记录执行情况——节点类型/描述/结果/函数调用/判断结果/时间/URL/LLM 推理，经 `Reporter.record_node` 被 M7 调用。
- **截图**：Action/Condition 节点返回前经 M1 截图当前页面状态，截图路径关联到对应节点报告。
- **两份报告**：执行报告（每节点结果 + 截图，不含 LLM 推理）与回溯报告（执行详情 + LLM 推理，不含截图），由 `Reporter.finalize` 生成。
- **可查询执行状态 `ExecState`**：运行进度 / 当前节点 / 已完成节点报告 / 完成标记，供 M9b 轮询。
- **持久化**：截图与报告文件落盘，路径可被 M9b 经 HTTP 提供。

## Capabilities

### New Capabilities

- `reporting`: 报告机制——节点执行记录、Action/Condition 截图、执行报告与回溯报告生成、可查询执行状态、报告/截图持久化，供 M7 记录、M9b 提供。

### Modified Capabilities

- 无（`openspec/specs/` 尚无既有 capability，本 change 引入首个 capability `reporting`）。

## Impact

- **依赖方新增消费方**：M7 编排器通过 `Reporter` 记录节点报告并维护 `ExecState`；M9b 后端读取报告/执行状态并提供给前端。
- **被依赖方（数据提供）**：M1 提供截图能力；M6 提供 `LeafTrace`（LLM 输入/推理过程/决策结果）供回溯报告；M7 提供节点执行数据。
- **受影响代码**：新增报告模块（Reporter/NodeReport/ExecReport/TraceReport/ExecState 等）；引擎 `run` 返回值增加两份报告；行为树遍历流程在节点退出前与叶子返回前接入记录/截图钩子。
- **文档**：同步更新 `docs/contract.md`（§5.8.3 相关实现说明）与 `docs/specs/M8-reporting.md`。