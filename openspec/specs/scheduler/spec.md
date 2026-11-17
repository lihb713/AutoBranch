# scheduler Specification

## Purpose

为行为树提供自动触发能力：按间隔/定时点执行，支持前置依赖树、失败重试、重启错过处理与执行来源标注；实际执行统一复用 M8 执行实例与 FIFO 队列。

## Requirements

### Requirement: 调度规则

系统 SHALL 支持创建、查询、更新、删除、启停调度规则。每条规则包含目标行为树、调度模式（`interval`/`cron`）、依赖树、静态入参、失败策略、错过策略和启用状态。

#### Scenario: 创建间隔规则

- **WHEN** 用户提交 `schedule_mode=interval`、间隔数值与单位
- **THEN** 系统保存规则并在到达间隔后自动触发目标行为树

#### Scenario: 创建定时规则

- **WHEN** 用户提交 `schedule_mode=cron` 与周期/时间（每周还需星期）
- **THEN** 系统按服务端本地时间在对应时间点触发

#### Scenario: 校验失败

- **WHEN** 规则缺少目标树、间隔/时间字段，或时间格式非法
- **THEN** 系统返回 422 并说明原因，不保存规则

### Requirement: 目标树与入参

系统 SHALL 在创建/更新规则时校验目标树存在且为 `published`，并通过 `validate_run_inputs` 校验静态入参；含不可由文本构造类型（`page_ref`/`object`）的目标树 SHALL 拒绝创建调度。执行时目标树必须为 `published`，草稿状态 SHALL 跳过执行并记录原因。

#### Scenario: 不可构造入参拒绝

- **WHEN** 目标树声明了 `page_ref` 入参
- **THEN** 创建调度返回 422，提示仅支持 ref 调用

#### Scenario: 目标转为草稿

- **WHEN** 调度到点时目标树处于 draft
- **THEN** 不创建执行实例，规则记录失败/跳过原因

### Requirement: 前置依赖

系统 SHALL 支持“依赖树全部成功后才执行目标树”。依赖树最近一次执行成功视为满足；运行中/排队中等待；从未执行或失败时创建依赖执行（`source=dependency`）。依赖树自身依赖 SHALL 递归处理。创建/更新规则时 SHALL 检测依赖图环（含目标自依赖与不经过目标树的环）并拒绝。

#### Scenario: 依赖成功后再执行目标

- **WHEN** 规则 A 依赖 B，B 最近一次执行不是 success
- **THEN** 先执行 B；B 成功后才执行 A

#### Scenario: 依赖失败

- **WHEN** 依赖树执行失败
- **THEN** 目标树不执行，按父规则 `on_failure` 重试或等下次调度

#### Scenario: 拒绝循环依赖

- **WHEN** 配置 A 依赖 B 且 B 依赖 A
- **THEN** 系统返回 422 拒绝配置

### Requirement: 失败重试

系统 SHALL 支持 `on_failure=immediate`（按 `retry_interval` 秒重试，最多 `max_retries` 次）与 `next_schedule`（等下一周期）。配置错误（草稿/入参非法/目标不存在）SHALL NOT 进入重试。

#### Scenario: 立即重试成功

- **WHEN** 目标执行失败且仍有重试次数
- **THEN** 系统在间隔后重新执行，成功后规则状态为 success

#### Scenario: 重试耗尽

- **WHEN** 立即重试次数耗尽仍失败
- **THEN** 规则状态为 failure，等待下一调度周期

### Requirement: 错过调度处理

系统 SHALL 在调度引擎启动时检查启用规则的 `last_run_at`：为空立即执行首次；过期周期按 `on_missed=run` 补跑一次或 `on_missed=skip` 跳过并更新 `last_run_at`。

#### Scenario: 停机后补跑

- **WHEN** 后端停机期间错过调度，重启后规则 `on_missed=run`
- **THEN** 启动后补跑一次

#### Scenario: 停机后跳过

- **WHEN** 规则 `on_missed=skip`
- **THEN** 不补跑，更新 `last_run_at` 并记录 skipped

### Requirement: 执行来源

系统 SHALL 在执行实例上记录 `source`（`manual`/`schedule`/`dependency`）与 `schedule_id`，并支持 `GET /api/runs?schedule_id=` 过滤。

#### Scenario: 调度执行标注

- **WHEN** 调度触发目标树
- **THEN** 执行实例来源为 schedule，记录规则 ID

#### Scenario: 依赖执行标注

- **WHEN** 调度触发前置依赖树
- **THEN** 执行实例来源为 dependency，记录父规则 ID

### Requirement: 执行记录双视图

系统 SHALL 为调度规则提供执行记录双视图：仅目标行为树（`source=schedule`）与含依赖（全部 `schedule_id` 关联实例）。前端弹窗 SHALL 支持切换视图，每条记录 SHALL 可跳转到对应执行详情页。

#### Scenario: 仅目标视图

- **WHEN** 用户打开调度规则执行记录并选择“仅目标行为树”
- **THEN** 只展示该规则触发的目标执行实例

#### Scenario: 含依赖视图

- **WHEN** 用户选择“含依赖”
- **THEN** 展示目标与前置依赖的全部关联执行实例，并可跳转执行详情

### Requirement: 执行详情展示调度来源

执行详情接口与页面 SHALL 展示执行来源（manual/schedule/dependency）；自动执行时 SHALL 展示关联调度规则名称、调度方式/频率与规则 ID；规则已删除时 SHALL 明确提示。

#### Scenario: 调度详情展示规则信息

- **WHEN** 用户查看由调度触发的执行详情
- **THEN** 页面展示“调度”来源、规则名称、每天/每 N 分钟等调度频率

### Requirement: 立即执行

系统 SHALL 提供 `POST /api/schedules/{id}/run` 立即执行目标树；该操作 SHALL NOT 检查前置依赖、SHALL NOT 修改 `last_run_at`，并返回执行实例 ID。

#### Scenario: 手动立即执行调度

- **WHEN** 用户在调度页点击“立即执行”
- **THEN** 系统创建一次 `source=schedule` 的执行实例并返回 run_id

### Requirement: 前端调度管理

前端 SHALL 提供 `/schedules` 页面：规则列表、创建/编辑、启停、删除、立即执行、执行记录；执行列表 SHALL 展示来源徽章。

#### Scenario: 查看执行记录

- **WHEN** 用户点击某规则的“执行记录”
- **THEN** 弹窗展示该规则关联的执行实例（编号/树名/状态/来源/耗时/开始时间）
