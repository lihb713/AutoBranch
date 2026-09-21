# run-instances-list 设计

## Context

现状（详见 proposal.md - Why）：`Run` 表只有 `tree_id`（CASCADE）/status/failure_reason/report_path，执行是瞬态——树列表点执行直接跳报告页，跑完即消失；`Engine.run` 只接收 `decl_inputs`（名→类型）而无实际入参值注入，`RunResult` 无出参字段；同树并发被 `RunService.start` 的 D8 去重（409）硬挡；执行经 FastAPI `BackgroundTasks` 触发。

约束：SQLite + `create_all`（database-rules §5，开发期）；树内容已存 `trees.content`（Text）；`TYPE_REGISTRY` 的 `TypeSpec.cast` 已表达"可否由文本构造"；前端现有 `TreeListPage` 页头混排页面级操作与跨页入口；E2E 强制要求（AGENTS.md）。

## Goals / Non-Goals

**Goals:**
- 把"执行"建模为自包含执行实例（内容快照 + 入参 + 出参 + 执行结构指纹），执行/重试均基于快照。
- 根级入参注入与出参返回的端到端链路（引擎 → 落库 → 展示）。
- 执行列表页 + FIFO 队列（全局并发上限可配置）+ 按快照重试 + 历史自包含保留。
- 类型可构造性单点派生（`GET /api/types`）+ 前端导航重构。

**Non-Goals:**
- 用户自定义类型注册机制（YAGNI，见 proposal；未来有真实需求再设计）。
- 经验回灌（Change C，依赖本 Change 的 `tree_content_hash`/`inputs`）。
- 排队实例的取消操作、列表分页/过滤、多用户权限。

## Decisions

### D1. Run 快照数据模型与 tree_id 语义

`runs` 表新增列：

| 列 | 类型 | 说明 |
|---|---|---|
| `content_snapshot` | Text | 触发时刻冻结的行为树 yaml 全文（执行/重试/查看快照的依据） |
| `tree_name_snapshot` | String(200) | 触发时刻的树名（删树后列表展示用） |
| `tree_content_hash` | String(64), index | 执行结构指纹（D2），短显 `#a3f9c1` |
| `inputs` | JSON | 用户提供的原始入参（JSON 安全值，retry 原样复用） |
| `outputs` | JSON, nullable | 运行结束的出参（JSON 安全序列化） |

`tree_id` 改 `nullable=True` + `ondelete="SET NULL"`：删除行为树时保留历史（列表用快照名展示，tree_id 仅承担"树仍存在时的编辑跳转"）。

- **为什么 content_snapshot 入 Text 列而非落盘**：与 §7"大字段落盘"的权衡——该规则针对报告正文（体积大、可重建）；行为树 yaml 是小结构化文档（`trees.content` 已同样入 Text 列），且快照必须随 run 自包含（retry/查看快照随时可取），落盘反而引入路径管理与丢失风险。属刻意取舍，非违反规则。
- **inputs 存原始串而非 coerce 后的对象**：retry 时只需重新反序列化原始值；对象类型（D4 后可能）不落库也避免序列化损失。

### D2. tree_content_hash = 执行结构指纹（规范节点图哈希）

`compute_tree_content_hash(content)`：解析文档 → 提取规范节点图 → SHA-256。

- 规范形态：`{"root": <id>, "nodes": {<id>: {…节点非 name 字段…}}}`。
- **计入**：节点 `type`、叶子执行内容（description/css_hint/set_targets）、结构槽位与控制字段、ref/FunctionCall 的 target/args/returns、执行配置；槽位引用目标节点 id 即结构边。
- **剔除**：树名、`inputs`/`outputs` 声明、节点 `name`、注释/空白/键顺序（`json.dumps(sort_keys=True)` 规范化，**列表顺序保留**——Sequence.actions/Branch.branches/args/returns 的顺序是语义）。
- 触发时计算一次（沿用执行前校验的解析结果，成本可忽略）；纯 id 改名产生安全"漏匹配"，不产生错误复用。

### D3. 根级入参注入与出参返回（引擎）

- `Engine.run` 新增 `run_inputs: dict[str, object] | None`：`enter_frame(root)` 后，对每个声明的入参名按类型 `coerce` 并 `space.write(root_frame, f"this/{name}", value, type)`——复用 ref 实参注入模式（traverser `_tick_ref`），叶子以 `Param.<名>` 读取。
- `RunResult` 新增 `outputs: dict[str, Any]`：遍历结束后按 `decl_outputs` 读根帧 `this/<出参名>`。
- 序列化边界：出参落库前做 **JSON 安全序列化**——标量原样；`PageRef` → `{"page_id","url"}`；其他对象 → `str(value)`（展示用途，防超长截断）。

### D4. 队列调度：ThreadPoolExecutor + DB 即队列

- `RunService` 懒创建 `ThreadPoolExecutor(max_workers=max_concurrent_runs)`；`max_concurrent_runs` 入 `autobranch.config.json`（默认 3）。
- `start()`：建 pending Run（含快照/入参）→ commit → `_drain()`。
- `_drain()`（进程内锁）：`running 数 < N` 时取最早 pending，**先置 running 再提交执行**（占位防并发双调度），submit 到 executor；执行结束（finalize/异常/fail）路径末尾再 `_drain()`。
- 重启恢复：沿用现有 `mark_interrupted`（pending/running 置 interrupted）——排队中任务重启即清，语义正确。

- 为什么不用 FastAPI `BackgroundTasks`：它随请求生命周期，无法表达"并发上限 + 排队"；executor 的 `max_workers` 天然约束"最多 N 个浏览器同时开着"。
- 备选：独立队列线程（多一个常驻线程与消息传递，收益低）；满则拒绝（用户明确要排队）。

### D5. 执行列表 API 与轮询

- `GET /api/runs`：返回实例列表（`created_at` DESC）——id、快照树名、status、inputs、`tree_content_hash` 短显、created_at/updated_at（耗时可派生）、进行中实例的 `progress`（经 `engine.get_exec_state` 取）。前端列表页在存在 active 实例时轮询该接口，行内状态/进度实时更新。
- 复用现有 `usePolling`；报告页/出参展示沿用现有 `/runs/{id}/state`、`/report`、`/trace`。

### D6. 类型可构造性单点派生

- `GET /api/types`：遍历 `TYPE_REGISTRY`，返回 `[{token, constructible}]`，`constructible = spec.cast is not None`。
- 前端：类型 token 下拉、入参表单、树列表"执行"按钮约束（含不可构造入参的树不渲染执行按钮）全部自该接口派生；`tokens.ts` 静态 `TYPE_TOKENS` 改为运行期获取 + 缓存。

### D7. 前端导航与页面

- `App.tsx` 引入**全局页签导航**组件（行为树管理 `/`、行为树执行列表 `/runs`、插件管理 `/plugins`）；"导入行为树"/"新建行为树"移入行为树管理页内容区（列表上方），退出页签栏。
- 新增 `RunListPage`：实例表 + 状态徽章 + 入参 + 耗时 + 指纹短显 + "重试"/"查看快照"/"删除"操作；轮询刷新。
- `TreeListPage`：执行按钮逻辑改为——无入参树直接跑；有可构造入参树弹入参对话框；含不可构造入参树不渲染按钮。
- `RunReportPage`：新增"出参"区（实例 outputs）；顶部加"重试"按钮。
- 重试 = `POST /api/runs/{id}/retry`（复制快照/入参新建 Run）；删除 = `DELETE /api/runs/{id}`（级联清理报告目录，`ReportService.cleanup_run` 现成钩子）。

### D8. 迁移方案（SQLite 首次改表）

`scripts/migrate_runs_snapshot.py`（幂等）：
1. 新列（content_snapshot / tree_name_snapshot / tree_content_hash / inputs / outputs）均为可空新增 → SQLite `ALTER TABLE ADD COLUMN`；
2. `tree_id` 改可空 + `SET NULL` → SQLite 不支持改列约束，走**表重建**（`PRAGMA foreign_keys=OFF` → 建 runs_new → 拷数据 → drop → rename → 重建索引/约束）；
3. 现有 pending/running 记录维持原样（启动 `mark_interrupted` 处理）。

数据库规则 §5 将 Alembic 留给"稳定期"，本次为开发期一次性迁移脚本，不动历史迁移。

## Risks / Trade-offs

- **并发浏览器资源**：每 run 一个浏览器，无限并发打爆资源 → 全局上限 `max_concurrent_runs`（默认 3）约束；上限可配置。
- **SQLite 多线程写竞争**：executor 多线程 + 独立会话并发写 → SQLite 串行化写事务，开发期规模可接受；迁移脚本在 `foreign_keys=OFF` 下重建表，注意先备份。
- **出参序列化有损**：对象类型出参仅 `str(value)` 展示、PageRef 折叠为 id+url → 明确"展示用途"，不承诺完整还原。
- **排队实例重启即失**：`mark_interrupted` 把 pending 置 interrupted → 排队任务重启丢失，属既有语义，可接受。
- **executor 生命周期**：进程退出时未完成的 run 被中断 → `mark_interrupted` 兜底；FastAPI shutdown 时需等待 executor（优雅关闭）。

## Migration Plan

1. 备份 `data/*.db`（如有）；2. 运行 `scripts/migrate_runs_snapshot.py`；3. 配置 `autobranch.config.json` 增加 `max_concurrent_runs`；4. 后端重启后验证 runs 列表与既有记录可读。回滚：恢复备份库并还原代码。

## Open Questions

- 执行列表是否要**分页/状态过滤**（实例可能很多）？可后补而不改本设计（接口加 query 参数即可），列为后续增强。
- 排队实例是否需要"取消排队"？本设计不含，用户未提，后续可加。