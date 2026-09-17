# plugin-management Specification

## Purpose

插件管理：后端提供插件 CRUD / 校验 / 关联查询 API 与插件表；前端提供插件管理页（列表 + Python 代码编辑器）。

## Requirements

### Requirement: 插件表与启动初始化

系统 SHALL 维护插件表，字段契约如下：
- `name`：插件名，UNIQUE 主键，≤128 字符，kebab-case；
- `kind`：`builtin` | `custom`（CHECK 约束，建索引）；
- `description`：能力说明，TEXT；
- `functions`：函数清单（JSON，≤16KB），**内容为函数全名**（`插件名.函数名`），启动扫描 / 重载时刷新；
- `source`：自定义插件源码，仅 `kind=custom` 存储（TEXT ≤1MB）；`builtin` 恒为 NULL（源码在文件系统，启动时才加载进库）；
- `created_at` / `updated_at`：UTC 时间戳，`updated_at` 每次变更更新。

引擎启动扫描预置插件时 SHALL 初始化 / 刷新 `builtin` 记录（只读）：写入 / 更新 `name` / `kind` / `description` / `functions`（全名），`source` 保持 NULL。`name` 全局唯一，用户自定义插件 SHALL NOT 与 `builtin` 同名（新增时校验拒绝并返回"已存在"）。

#### Scenario: 启动初始化插件表
- **WHEN** 引擎启动
- **THEN** 预置插件记录写入插件表（`kind=builtin`，`source` 为 NULL）；启动后 `GET /api/plugins` 返回 ≥N 条且每条含 `kind` 字段与全名函数清单

#### Scenario: 预置插件只读
- **WHEN** 尝试修改预置插件
- **THEN** 系统拒绝

#### Scenario: 自定义插件不得与预置同名
- **WHEN** 新增自定义插件名与某预置插件相同
- **THEN** 校验拒绝并返回"已存在"
### Requirement: 插件 API

系统 SHALL 提供插件 API：列出（含 kind）、读源码、新增、更新、删除、校验。插件列表返回的函数清单 SHALL 为**全名**（`插件名.函数名`）。系统 SHALL 额外提供**函数清单 API** `GET /api/functions`：跨插件聚合返回全部已注册函数的结构化定义（全名 / 所属插件 / 裸函数名 / 说明 / 参数 / 返回值），供编辑器函数选择器与提示使用；预置与自定义插件的函数 SHALL 一并返回。

#### Scenario: 校验自定义插件
- **WHEN** 保存自定义插件
- **THEN** 后端校验语法与约束（仅标准库、不 import 其他插件 / `common` / 三方库），返回错误明细（含行号 / 列号 / 错误类型 / 信息 / 约束）；无错误才落库

#### Scenario: 新增自定义插件
- **WHEN** 提交新插件源码
- **THEN** 校验通过后写入插件表（`kind=custom`）并重载生效

#### Scenario: 保存失败不落库
- **WHEN** 校验或重载失败
- **THEN** 前端报错（含行号与错误明细）且源码不落库、不保留错误版本；仅保存成功才写入插件表并记录版本

#### Scenario: 获取函数清单
- **WHEN** 请求 `GET /api/functions`
- **THEN** 返回全部已注册函数（含预置与自定义）的全名与结构化定义
### Requirement: 前端插件管理页

系统 SHALL 提供前端插件管理页：插件列表（标记预置 / 自定义）、Python 代码编辑器（语法高亮 + 基础补全）、新增 / 编辑 / 删除；保存时后端校验，失败时前端显示行号与错误信息。

#### Scenario: 编辑并保存插件
- **WHEN** 用户在编辑器保存自定义插件
- **THEN** 后端校验（返回行号 / 列号 / 错误类型 / 约束），通过则落库并重载生效；失败则前端显示错误明细（行号 + 信息 + 约束说明），源码不保存

#### Scenario: 列表区分来源
- **WHEN** 打开插件管理页
- **THEN** 列表展示预置与自定义插件并分别标记
### Requirement: 删除关联提示

系统 SHALL 在删除插件时列出引用该插件的行为树，供用户决定；若插件正被运行中的行为树引用，系统 SHALL 拒绝删除。确认删除后，系统 SHALL 批量清理（**持久化修改**行为树文档）其中对该插件函数的 FunctionCall 引用（`function` 置空），并在后续清晰度校验中报告"悬空引用"——因为插件已删除，文档中残留引用即错误。

#### Scenario: 删除被引用的插件
- **WHEN** 删除被某行为树引用的插件（且无运行中引用）
- **THEN** 弹窗列出关联行为树；确认后删除插件，并批量将对应 FunctionCall 引用置空（持久化写入行为树文档）
