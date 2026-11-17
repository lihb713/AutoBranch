## Context

M8 已有 `RunService.start()`（快照 + 全局并发 FIFO 队列）和 `_finalize()` 终态落库；M9 已有执行列表/报告页。M10 不需要新的执行器，只需要一个轻量触发器。

约束：

- 单进程 SQLite + FastAPI；不引入外部进程/服务。
- 调度不能绕过现有队列与快照机制。
- 行为树可能被删除/转草稿；调度目标必须始终是当前 `published` 版本。
- 项目要求中文文档、独立环境测试、更新 specs/OpenSpec。

## Goals / Non-Goals

**Goals**

- 定时（interval/cron）自动触发。
- 前置依赖 DAG（全部成功），依赖树递归；配置时检测环。
- 失败立即重试 / 等下次调度；重启错过补跑或跳过。
- 执行来源标注与按调度规则查看历史。
- 前端调度管理页与执行来源列。

**Non-Goals**

- 不做任意条件表达式 / AND-OR-NOT / LLM 条件判断。
- 不做多进程调度 leader 选举（当前单进程部署；守护线程在 lifespan 内启动）。
- 不做从失败节点恢复执行。
- 不做时区字段（统一服务端本地时间）。

## Decisions

### D1：独立 `ScheduleRule` 表，不写入行为树文档

一棵树可有多条规则，规则变化不应污染 DSL；`dependencies`/`inputs` 用 JSON 列。

### D2：所有触发统一走 `RunService.start`

调度目标 `source="schedule"`，依赖 `source="dependency"`；由现有 `_drain` 控制并发，M10 不维护第二套执行槽位。

### D3：单守护线程 + 内存队列 + 完成回调

- 默认 10s tick（`scheduler_tick_seconds` 可配置）。
- 等待队列（依赖未满足）与 ready FIFO；`RLock` 保护。
- `RunService.set_on_run_complete` 在终态调用引擎；避免轮询 run 表。
- 单元测试直接调用 `tick_once(now)`，可注入时钟。

### D4：依赖语义为“最近一次执行结果”

- 成功：满足；运行中/排队中：等待；从未执行/失败：创建依赖任务。
- 同一依赖树同时只创建一个依赖任务，避免多个父任务重复触发。
- 依赖任务本身不重试；失败交给父规则按父规则策略处理，避免双重重试放大。

### D5：`last_run_at` 记录触发时间

每次到点先持久化 `last_run_at` 再创建任务；即使执行失败也代表该周期已触发。启动时按 `on_missed` 处理过期周期。

### D6：轻量迁移

旧库启动时 `ALTER TABLE runs ADD COLUMN source/schedule_id` + 索引；不删除数据库。`schedule_rules` 由 `create_all` 创建。

### D7：调度页“立即执行”不检查依赖

对应手动触发语义，`POST /api/schedules/{id}/run` 直接 `RunService.start`，不改变 `last_run_at`，不进入自动重试。

## Risks / Trade-offs

- [守护线程与 uvicorn 多 worker] → 当前单进程部署；若未来多 worker，需要 DB 租约或独立 scheduler 进程。
- [内存等待队列重启丢失] → 下个调度周期重建；已触发但未完成的依赖可能出现重复执行，按“最近一次成功”语义可接受。
- [本地时间/DST] → 单机内部工具，暂不引入时区；后续可扩展 IANA 时区字段。
- [静态入参含敏感值] → 入参 JSON 入 schedule_rules；当前无认证/加密，按本地单用户假设。
