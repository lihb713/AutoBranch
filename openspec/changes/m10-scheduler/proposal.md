## Why

当前行为树只能手动触发，无法按周期自动运行，也无法保证“前置检查/汇总树”先成功。需要新增 M10 定时调度模块，把自动触发、依赖顺序、失败重试与重启恢复纳入管理系统，同时保持执行仍走现有快照 + FIFO 队列。

## What Changes

- 新增 `autobranch/scheduler/`：`ScheduleRule` 模型、CRUD 校验、依赖环检测、调度引擎（守护线程 + 等待/执行队列 + RunService 完成回调）。
- 支持 `interval`（秒/分/时/天）与 `cron`（每小时第 N 分钟 / 每天 HH:MM / 每周某天 HH:MM）。
- 支持前置依赖树（全部成功才执行目标；依赖树递归处理；同一依赖同时只跑一个）。
- 支持失败 `immediate` 重试（次数/间隔）与 `next_schedule`；重启后按 `on_missed` 补跑或跳过。
- `runs` 新增 `source`（manual/schedule/dependency）与 `schedule_id`；`GET /api/runs?schedule_id=` 过滤。
- `RunService` 新增来源参数、完成回调、按调度过滤；旧库轻量补列。
- 新增 `/api/schedules` CRUD/启停/立即执行/执行记录 API。
- 前端新增 `/schedules` 调度管理页；执行列表新增来源列。
- 更新 `docs/specs/M8-management-backend.md`、`M9-frontend-ui.md`、新增 `M10-scheduler.md`、`docs/contract.md` 与 OpenSpec specs。

## Capabilities

### New Capabilities
- `scheduler`: 定时/依赖调度规则管理与自动触发执行。

### Modified Capabilities
- `run-instances`: 执行实例增加来源标注与按调度规则过滤。

## Impact

- 后端：`autobranch/scheduler/`、`server/main.py`、`server/models/run.py`、`server/services/runs.py`、`server/routers/runs.py`、`server/schemas/run.py`、`server/db.py`、`autobranch/config.py`。
- 前端：`api/schedules.ts`、`types/schedule.ts`、`features/schedules/`、`GlobalNav`、`App`、`RunListPage`、`index.css`。
- 数据库：新增 `schedule_rules` 表；`runs` 补 `source/schedule_id`。
- 测试：调度时间/依赖/引擎/API/前端组件/E2E。
