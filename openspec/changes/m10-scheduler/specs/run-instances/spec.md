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
