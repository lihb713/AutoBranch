# M10 · 定时调度模块 Spec

> 依据需求 `temp/M10定时调度.md`，结合现有 M8 管理后端 / M9 前端实现。
> **实现状态：后端调度引擎、API、前端调度管理页、执行来源标注与测试已落地 ✅**

## 1. 概述

M10 为行为树增加**自动触发**能力：按固定间隔/定时点触发目标行为树，支持前置依赖树（全部成功后才执行目标）、失败立即重试、重启后错过调度处理，并在执行实例上标注来源。

调度模块**只负责“何时触发、依赖顺序”**；实际执行仍统一走 M8 `RunService.start()` 的 FIFO 队列与快照机制，不绕过现有执行链路。

实现位置：`autobranch/scheduler/` + `autobranch/frontend/src/features/schedules/`。

## 2. 设计约束

1. **系统模块**：M10 是后端固有模块，不是插件。
2. **轻量嵌入式**：单守护线程 + SQLite，无额外进程/外部服务/第三方 cron 依赖。
3. **无逻辑表达式**：前置依赖为“全部成功”语义，不支持 AND/OR/NOT。
4. **手动触发不影响调度周期**：行为树页面手动执行不检查依赖；调度页「立即执行」同样不检查依赖，也不更新 `last_run_at`。
5. **统一执行入口**：调度触发、依赖触发都调用 `RunService.start(source=..., schedule_id=...)`。

## 3. 调度模型

### 3.1 调度规则（`schedule_rules`）

| 字段 | 说明 |
|---|---|
| `id` | 主键 |
| `name` | 规则名称（≤128） |
| `target_tree_id` | 目标行为树（FK → trees，ON DELETE CASCADE） |
| `schedule_mode` | `interval` / `cron` |
| `interval` / `interval_unit` | 间隔数值 / `seconds|minutes|hours|days` |
| `cron_period` | `hour` / `day` / `week` |
| `cron_time` | hour：`:MM`；day/week：`HH:MM` |
| `cron_weekday` | 0=周日，1=周一 … 6=周六（仅 week） |
| `dependencies` | 前置依赖行为树 ID 列表（JSON） |
| `inputs` | 调度触发时使用的静态 JSON 入参 |
| `on_failure` | `immediate` / `next_schedule` |
| `max_retries` / `retry_interval` | 立即重试次数 / 重试间隔（秒） |
| `on_missed` | `run`（补跑一次）/ `skip`（跳过） |
| `last_run_at` | 最近一次**调度触发时间**（非完成时间） |
| `last_run_id` | 最近一次触发产生的执行实例 |
| `last_status` | `pending/running/retrying/success/failure/skipped` |
| `last_error` | 最近失败/跳过原因 |
| `enabled` | 启用开关 |
| `created_at/updated_at` | 时间戳 |

### 3.2 调度模式

- **interval**：`last_run_at + interval * unit`。
- **cron hour**：每小时第 N 分钟；支持 `":30"` / `"30"` / `"09:30"`（取分钟）。
- **cron day**：每天 `HH:MM`。
- **cron week**：每周指定 `cron_weekday` 的 `HH:MM`。
- 时间统一按项目配置时区（`timezone`，默认 `Asia/Shanghai`）解释；数据库存本地 naive 时间。

### 3.3 前置依赖

1. 调度任务创建时读取规则 `dependencies`。
2. 每个依赖树取其**最近一次执行结果**：
   - `success` → 依赖满足；
   - `pending/running` → 等待该执行结束；
   - 从未执行/失败 → 触发该依赖树（`source="dependency"`）。
3. 所有依赖满足后才提交目标树；依赖失败时目标不执行，按父规则 `on_failure` 重试或等下次调度。
4. 依赖树自身的调度依赖会递归展开（DAG）；同一依赖树同时只触发一个执行，避免依赖风暴。
5. 配置依赖时 DFS 检测环：目标树自身依赖、跨规则环（包括不经过目标树的环）均拒绝（422）。

### 3.4 失败与重试

- `immediate`：目标执行失败后按 `retry_interval` 秒后重试，最多 `max_retries` 次；重试耗尽后 `last_status=failure`，等下一次调度。
- `next_schedule`：不立即重试，等下一调度周期。
- 依赖任务本身不重试；依赖失败由等待它的父规则按父规则策略处理。
- 配置错误（目标草稿/目标不存在/入参不可构造）不进入重试循环。

### 3.5 错过调度

- 调度线程启动时逐条检查启用规则：
  - `last_run_at=null` → 立即触发首次执行；
  - 计算下次应触发时间，若当前已过：
    - `on_missed=run` → 补跑一次；
    - `on_missed=skip` → 不补跑，更新 `last_run_at=now`、`last_status=skipped`。
- 每次触发前先持久化 `last_run_at`，避免异常/重启导致同周期重复触发。
- 内存等待/执行队列在重启后丢失；未完成依赖任务随下一调度周期重新创建。

### 3.6 执行来源

`runs` 新增：

| 字段 | 说明 |
|---|---|
| `source` | `manual` / `schedule` / `dependency` |
| `schedule_id` | 关联调度规则 ID（可空） |

- 手动执行：`manual`；
- 调度目标：`schedule`；
- 前置依赖：`dependency`；
- 重试保留原实例来源。
- 执行列表展示来源徽章；`GET /api/runs?schedule_id=` 按规则过滤。

## 4. 调度引擎

```
SchedulerEngine（daemon thread，默认 10s tick）
  ├─ _check_due_rules：到点/首次/错过 → 创建任务
  ├─ _advance_waiting：检查依赖最近执行，必要时创建依赖任务
  ├─ _dispatch_ready：校验目标正式版 + 入参 → RunService.start
  └─ on_run_complete(run_id, status)：RunService 完成回调 → 更新依赖/重试
```

- 等待队列：依赖未满足的任务；执行队列：依赖已满足的 FIFO 任务。
- `threading.RLock` 保护内存队列；回调通过 `RunService.set_on_run_complete` 注册。
- 执行并发完全复用 `RunService` 的全局 `max_concurrent_runs` + FIFO 队列；M10 不单独放开并发。
- 测试可注入 `now` 并直接调用 `tick_once()`。

## 5. API

```
GET    /api/schedules                 列出调度规则
POST   /api/schedules                 创建（201）
GET    /api/schedules/{id}            详情
PUT    /api/schedules/{id}            全量更新
DELETE /api/schedules/{id}            删除（204）
PATCH  /api/schedules/{id}/toggle     启用/停用
POST   /api/schedules/{id}/run        立即执行（202 → {"run_id": n}；不检查依赖、不改 last_run_at）
GET    /api/schedules/{id}/runs       该规则关联执行实例（?source=schedule|dependency）
GET    /api/runs?schedule_id={id}     执行实例按规则过滤（可叠加 ?source=）
GET    /api/runs/{id}                 执行详情含关联调度摘要（规则名/调度方式）
```

校验规则：

- 目标树必须存在且为 `published`；依赖树必须存在；目标不能依赖自身。
- 依赖图不得成环。
- `interval` 必须提供数值+单位；`cron` 必须提供周期+时间；week 必须提供星期。
- 静态入参通过 `validate_run_inputs`：`page_ref` 不可构造 / 缺少必填入参 → 422（与手动执行一致）；`array`/`object` 支持 JSON 数组/对象文本，`generics` 原样接收。

## 6. 前端

- 全局导航新增「调度管理」`/schedules`。
- 调度列表：名称/目标树/调度方式/下次执行/上次结果/启用开关/操作。
- 新建/编辑弹窗：目标树（仅正式版且入参可构造）、间隔或 cron、前置依赖多选、失败策略、错过策略、按目标树 `inputs` 动态渲染的入参表单、启用。
- 操作：立即执行、执行记录弹窗、启停、编辑、删除。
- 编辑与执行记录均为**居中弹窗**（遮罩层，支持点击遮罩关闭）。
- 执行记录弹窗提供两种视图：「仅目标行为树」（`source=schedule`）与「含依赖」（全部关联实例），每条记录可跳转 `/runs/{id}` 执行详情。
- 执行列表新增「来源」列：手动/调度/依赖；执行详情页展示来源，自动执行时展示关联调度规则名称/调度频率/规则 ID。

## 7. 数据库与迁移

- `ScheduleRule` 由 `create_all` 自动建表。
- 旧库 `runs` 缺 `source/schedule_id` 时，启动轻量 `ALTER TABLE` 补列并建 `ix_runs_schedule_id` 索引（不删库、不丢行为树）。
- 删除行为树级联删除其调度规则；执行历史仍按现有 `tree_id SET NULL` 保留。

## 8. 与设计文档的差异/优化

1. **并发默认值保持 3**：设计建议改为 10，但本机浏览器自动化资源有限，保持现有默认，仍可通过 `max_concurrent_runs` 配置。
2. **增加静态入参**：设计未覆盖带参行为树的定时执行；M10 增加 `inputs` 并在创建/执行时校验。
3. **增加状态字段**：`last_status/last_error/last_run_id`，便于前端展示与排障。
4. **轻量迁移**：不采用“删除数据库重建”，避免误删行为树。
5. **依赖任务不重复重试**：依赖任务失败交给父规则重试，避免父/子双重重试放大。
6. **时间使用本地时间**：不引入时区字段；与当前单机开发场景一致。
7. **立即执行接口**：设计没有手动触发调度规则，新增 `POST /schedules/{id}/run` 便于验证与运维。

## 9. 验收标准

- [x] interval / cron 规则到点自动触发，且只执行最新正式版。
- [x] 首次调度（`last_run_at=null`）自动执行。
- [x] 前置依赖全部成功后才执行目标；依赖失败目标不执行。
- [x] 依赖环配置被拒绝。
- [x] 失败按 `immediate` 重试；耗尽后等下次调度。
- [x] 重启后按 `on_missed` 补跑或跳过。
- [x] `runs.source/schedule_id` 正确标注，执行列表可按规则过滤。
- [x] 前端调度管理页 CRUD/启停/立即执行/执行记录可用。
- [x] 旧库轻量迁移不丢行为树。

## 10. 测试

- `tests/scheduler/test_timecalc.py`：interval/小时/天/周/时间格式。
- `tests/scheduler/test_deps.py`：依赖图聚合与环检测。
- `tests/server/test_scheduler_engine.py`：到点触发、依赖顺序、立即重试、错过补跑/跳过、来源。
- `tests/server/test_scheduler_api.py`：CRUD、环拒绝、不可构造入参、立即执行、按规则过滤。
- `autobranch/frontend/src/features/schedules/ScheduleListPage.test.tsx`：列表/新建/启停/立即执行/执行记录。
- `autobranch/frontend/e2e/schedules.spec.ts`：调度页 → 自动触发/立即执行 → 执行列表来源 → 报告页。
