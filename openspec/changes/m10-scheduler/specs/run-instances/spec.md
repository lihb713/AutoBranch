# run-instances delta · M10

## ADDED Requirements

### Requirement: 执行来源与调度过滤

系统 SHALL 在执行实例上记录来源 `source`（`manual` / `schedule` / `dependency`）与关联调度规则 `schedule_id`；手动触发为 `manual`，调度目标为 `schedule`，前置依赖为 `dependency`；重试保留原实例来源。`GET /api/runs?schedule_id={id}` SHALL 支持按调度规则过滤执行实例。

#### Scenario: 执行列表展示来源

- **WHEN** 用户查看执行列表
- **THEN** 每行展示来源徽章（手动/调度/依赖）

#### Scenario: 按调度规则过滤

- **WHEN** 用户请求 `GET /api/runs?schedule_id=3`
- **THEN** 只返回 schedule_id 为 3 的执行实例


### Requirement: 时间戳时区

系统 SHALL 按项目 `timezone` 配置（默认 `Asia/Shanghai`）写入并返回执行实例的 `created_at`/`updated_at`，执行列表与详情页展示该时区的本地墙钟时间；旧库中由 SQLite 写入的 UTC 审计列 SHALL 在启动时一次性迁移为本地时间。

#### Scenario: 执行列表显示北京时间

- **WHEN** 项目未显式配置 `timezone`
- **THEN** 创建于北京时间 23:23 的执行实例在执行列表中显示为 23:23，而不是 UTC 15:23

#### Scenario: 旧库迁移不重复偏移

- **WHEN** 旧库首次以新版本启动
- **THEN** UTC 审计列被转换为本地时间并写入迁移标记，后续启动不再重复转换
