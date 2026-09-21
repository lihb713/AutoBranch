# experience-feedback 设计

## Context

现状（详见 proposal.md - Why）：`LeafTrace`（reporting/models.py）已记录每个叶子调用 LLM 的完整追踪（llm_input / reasoning / decision / calls / terminator）；`execute_leaf`（leaf_agent/executor.py）先做 `_resolve_get_refs` 替换 `Param.x` 得到实际描述、再 `build_user_message` 拼用户消息；`Reporter.exec_state()` 返回含 `llm_trace` 的 `NodeReport` 列表（引擎内存可读）；Change A 为 `Run` 提供 `content_snapshot`/`tree_content_hash`/`inputs`。

**关键发现**：`_build_leaf_result` 里 `LeafTrace.llm_input["description"]` 记录的是 `node.description`（**未替换模板**），而非实际喂给 LLM 的**替换后描述**。经验匹配的节点钥匙必须是"替换后描述"（才携带真实入参/中间值），因此需先修正该记录为替换后文本。

## Goals / Non-Goals

**Goals:**
- 经验表 + 整树成功时的节点级采集与蒸馏（去 ref 化）。
- 节点粒度惰性匹配（三钥匙）+ 最近一次注入；注入姿态为"参考而非指令"。
- 按匹配组老化（保留最近 N 条）+ 全局开关，均可配置。

**Non-Goals:**
- 节点级成功采集（仅整树成功）与多数投票（保守默认，后续可放宽）。
- 前端经验展示 UI（可选增强，本 Change 以引擎侧为主）。
- 自定义类型注册机制（Change A 已定 YAGNI）。

## Decisions

### D1. experiences 数据模型

```
experiences
  id                PK
  run_id            FK → runs（ondelete=CASCADE，删实例级联删经验）
  tree_content_hash String(64), index
  inputs_norm       Text    归一化入参 JSON（sort_keys，做相等比较）
  node_desc         Text    叶子替换 Param 后的 description（节点身份）
  node_type         String   action / condition
  tool_calls        JSON    蒸馏后的成功调用序列（去 ref 化）
  decision          Text    最终决策（结果: 成功/真/假）
  created_at        采集时间（来源 run 结束时间）
```

- 匹配组索引 `(tree_content_hash, inputs_norm, node_desc)` 支撑节点粒度惰性查询。
- `inputs_norm` 存归一化 JSON 串而非对象，保证相等比较稳定。

### D2. 修正 LeafTrace 记录替换后描述

`_build_leaf_result` 的 `llm_input["description"]` 由 `node.description` 改为**替换后**的 `description`（即实际发送给 LLM 的文本）。理由：匹配钥匙必须携带真实值。影响：回溯报告该字段从"模板"变为"实值"，**相关回归测试需同步更新**；对用户是更准确的"LLM 实际看到什么"。

### D3. 采集与蒸馏（RunService._finalize 成功路径）

- 触发点：`_finalize` 置 `success` 时，若 `experience_feedback` 开启，经 `self._engine.get_exec_state(run_id)` 取结构化 `NodeReport` 列表（含 `llm_trace`）。
- 对每个 `node_type ∈ {Action, Condition}` 且 `result == success` 的叶子：蒸馏一条经验。
- **蒸馏规则**（D4）后插入；随后执行**老化清理**（D5）。
- 为什么不放进引擎层：采集是"run 结束的副作用"，属服务端职责；引擎只消费 `LeafTrace`，不写 DB。

### D4. 蒸馏：只留成功路径骨架 + 去 ref 化

- 成功调用序列：取 `llm_trace.calls` 中 `success=True` 的调用（function + 关键参数 + 结果摘要，截断）。
- **去 ref 化**：参数/结果中的运行时标识（`ref=N`、语义图坐标/scope）弱化为目标元素描述——参数里出现的 ref 编号按当前语义图中的元素文本替换为"目标元素描述"，或直接省略不可解释的编号；绝不把 `ref=1` 当常量喂给 LLM。
- 决策：`llm_trace.decision`（`结果: 成功/真/假`）。
- 剔除：`reasoning`、失败的中间调用、`screenshot_path`、时间戳。

### D5. 匹配查询与注入链路

```
RunService 触发时构建查询闭包（绑定该 run 的 hash + inputs_norm）
  → EngineService.run(..., experience_lookup=闭包)
  → EmbeddedEngineService 注入 RunConfig.experience_lookup
  → make_default_leaf_executor 透传 → LeafContext.experience_lookup
  → execute_leaf 在 _resolve_get_refs 后:
      ref = ctx.experience_lookup(替换后 description)   # 三钥匙 + LIMIT 1
      build_user_message(..., reference=ref)            # ref 为 None 不渲染
```

- 查询：`WHERE tree_content_hash = :h AND inputs_norm = :i AND node_desc = :d ORDER BY created_at DESC LIMIT 1`。
- 注入姿态：参考段附"仅供参考，以当前语义图为准；与当前页面状态不符时忽略经验"。
- 关闭/未命中：闭包返回 `None` → 用户消息与现状逐字一致。
- 抽象层：`EngineService.run` 增加可选 `experience_lookup` 参数（Mock 记录不执行），保持 mock 可测。

### D6. 老化清理

采集插入后，按匹配组 `(tree_content_hash, inputs_norm, node_desc)` 分组，Python 侧删除各组"按 created_at/id 排序超出 N 条"的旧记录。N = `experience_retention`（默认 5）。不用 SQL 窗口函数，Python 分组简单可测、跨 SQLite 兼容。

### D7. 配置与关闭路径

- `experience_feedback`（bool，默认 true）：关闭时 `_finalize` 不采集、`EmbeddedEngineService` 不注入回调 → 叶子行为与现状完全一致。
- `experience_retention`（int，默认 5）：老化阈值。
- 二者入 `autobranch.config.json`（`AutoBranchConfig`）。

## Risks / Trade-offs

- **回溯报告字段变化**：`llm_input.description` 模板→实值，属语义修正；需同步既有回归测试（提示词回归断言若以模板断言会失败）。
- **每叶子一次 DB 查询**：命中查询有索引，叶子数少，开销可忽略；开关关闭时零查询。
- **经验含敏感入参值**：替换后描述可能含密码等入参值，经验存本地库 → 属本地存储、与 `trees.content` 同级风险；文档注明，不做脱敏（用户自管）。
- **重启后不回填**：采集仅在 run 完成当下做，历史 run 不回填经验 → 新功能上线后从下一次成功 run 开始积累，符合预期。
- **Mock 引擎状态**：`MockEngineService.get_exec_state` 需能返回含 `completed` 的终态，采集逻辑依赖它；测试注入含 `llm_trace` 的 `NodeReport`。

## Migration Plan

`experiences` 为**新表**，`create_all` 自动创建，无既有表迁移；配置新增两键（缺省默认值兼容）。回滚：关闭 `experience_feedback` 即整体停用（不删除表、不清经验）。

## Open Questions

- 无阻塞项。多数投票 / 节点级成功采集为后续增强，不改本设计的查询与注入骨架。