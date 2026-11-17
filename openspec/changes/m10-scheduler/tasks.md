# m10-scheduler 任务

- [x] 1.1 新增 `ScheduleRule` 模型与 `schedule_rules` 表（interval/cron、依赖、inputs、失败/错过策略、last_* 状态）
- [x] 1.2 时间计算（interval/cron hour/day/week）与依赖环检测
- [x] 1.3 调度规则 CRUD 服务、Pydantic schema、`/api/schedules` 路由
- [x] 2.1 `RunService.start` 增加 `source/schedule_id`、`set_on_run_complete`、`list_runs(schedule_id)`
- [x] 2.2 `runs` 模型/迁移/API schema 增加来源字段
- [x] 2.3 `SchedulerEngine`：到点检查、错过处理、依赖 DAG、立即重试、完成回调、立即执行
- [x] 2.4 FastAPI lifespan 启动/停止调度引擎并注册完成回调
- [x] 3.1 前端调度管理页（列表/新建/编辑/启停/删除/立即执行/执行记录）
- [x] 3.2 全局导航 `/schedules`、执行列表来源列、样式
- [x] 4.1 后端单元/引擎/API 测试
- [x] 4.2 前端组件测试
- [x] 4.3 Playwright E2E 调度链路
- [x] 5.1 更新 docs/specs、contract、OpenSpec 主 spec 与 change
- [x] 5.2 运行 pytest/ruff/前端 typecheck/lint/test/build
