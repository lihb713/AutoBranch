# experience-feedback 提案

## Why

LLM 的随机性导致"同一行为树成功一次后重跑可能失败"——每次叶子执行都是全新会话，从零推理。若保留成功执行经验，并在**同条件**（同行为树快照 + 同入参 + 同节点）下把"上次成功的做法"作为参考注入叶子，可降低重跑的不确定性。经验是**蒸馏的参考**而非回溯报告原文：回溯报告含大量推理噪声、失败尝试与截图等冗余信息，直接投喂会把 LLM 带偏。

## What Changes

- **经验采集（三钥匙身份）**：新增 `experiences` 表，在**整树成功**的 run 结束时，从 `LeafTrace` 抽取每个叶子节点的一条经验记录，携带：`tree_content_hash`（执行结构指纹，定义见 run-instances-list 提案：仅节点图 + 节点内容 + 执行配置，排除树名/节点名/入参/出参）、归一化 `inputs`（入参直比）、叶子**替换 `Param` 之后**的 description（节点身份）。三者共同构成命中条件——**改树执行结构或改入参即失效**；树走 A→B→A 改回后旧经验重新可命中。
- **蒸馏内容**：只保留**成功路径的骨架**——叶子执行中成功的工具调用序列（function + 关键参数 + 结果摘要）与最终决策（`结果: 成功/真/假`）；不收录 LLM 推理文本、失败尝试、截图路径、时间戳。**运行时标识（如 ref 编号、语义图坐标）在蒸馏时弱化为目标元素描述**（如 `click(ref=1)` → `click 目标元素"登录按钮"`），避免把运行时实例当常量喂给 LLM，防止页面变化后锚定失效。
- **注入姿态（参考而非指令）**：叶子用户消息末尾追加"上次成功执行本节点的参考"段，明示"**仅供参考，以当前语义图为准；与当前页面状态不符时忽略经验**"——LLM 无需自行诊断"路径错 vs 经验失效"，指令预设"图为准、经验不符即弃"；经验只在状态稳定时把初始方向偏向已知成功路径。注入经 `LeafContext` 新增的回调解析（叶子侧无 DB 依赖，由服务端注入查询闭包）。
- **匹配的简洁性**：入参一致性无需单独逻辑——经验行天然携带其来源 run 的 `(tree_content_hash, inputs)`，新 run 以自身快照哈希 + 入参查询，入参对不上的经验行自然查不出来；节点级再以替换后 description 精确匹配。
- **匹配流程（节点粒度惰性）**：注入不是 run 开局全量，而是**每个叶子执行时**做一次查询——`tree_content_hash`/`inputs_norm` 在 run 开始绑入查询闭包，`node_desc`（替换 Param 后的实际描述）在该叶子执行那一刻算出；三钥匙合并为一条查询，`ORDER BY created_at DESC LIMIT 1` 从历史集合中选出**最近一条**注入。命不中就完全不注入，该叶子行为与无经验完全一致。`experiences` 表是**全部成功历史的集合**（每成功 run 每叶子一行），注入永远是"从集合里筛出的单条"。
- **老化机制**：经验表按匹配组（`tree_content_hash` + `inputs_norm` + `node_desc`）**只保留最近 N 条**，每次成功采集后删除超出部分（更旧的自然老化）——与节点粒度匹配对齐，保证 `LIMIT 1` 总有最近 N 条可选，表增长有界（N × 不同匹配组数）。
- **配置项**：`experience_feedback`（开/关，默认开；关闭时既不采集也不注入）+ `experience_retention`（每组保留条数 N，默认 5），入 `autobranch.config.json`，允许用户调整。
- **选择口径（保守默认）**：只从整树成功的 run 收集；多次命中取**最近一次**成功经验。二者作为设计默认，可后续放宽（节点级成功 / 多数投票）。

**BREAKING**：无（纯新增能力；叶子无经验命中时行为与现状完全一致）。

## Capabilities

### New Capabilities

- `experience-feedback`: 成功执行经验的采集（三钥匙身份 + 蒸馏 + 老化）、存储（experiences 表）与注入（叶子 prompt 参考段，节点粒度惰性匹配）。

### Modified Capabilities

- `leaf-agent`: 叶子提示词构建 SHALL 支持可选注入"上次成功参考"段（仅同快照 + 同入参 + 同节点时命中）；执行上下文 SHALL 支持注入经验查询回调，无经验命中时保持现有行为。

## Impact

- **引擎层 M6**：`autobranch/leaf_agent/{prompts,executor,models}.py`（参考段渲染、`LeafContext` 回调、`LeafTrace` 消费）。
- **管理后端 M8**：新增 `experiences` 模型与采集 service（run 结束钩子 + 老化清理）、`EmbeddedEngineService` 注入查询闭包（绑定 run 哈希/入参）、配置项（`experience_feedback`/`experience_retention`）、可选经验 API（查看某 run 产生的经验）。
- **前端 M9**：报告页展示"本次参考了哪些经验"（可选增强）；本 Change 以引擎侧为主。
- **E2E/实验**：验证"注入参考经验后同树重跑成功率提升"（可先用 mock LLM 断言参考段确实进入 prompt，再做实机对比）。
- **文档**：`docs/contract.md` §5.7.2 叶子执行、`docs/specs/M6-leaf-agent.md`、M8 相关章节。

**依赖**：依赖 Change A 提供的 `content_snapshot`/`tree_content_hash`/归一化 `inputs`（实例身份）作为经验匹配基础。