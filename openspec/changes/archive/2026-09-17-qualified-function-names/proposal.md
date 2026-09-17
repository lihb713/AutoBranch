## Why

FunctionCall 节点的函数名当前由用户**手动填写**自由文本，且只用**裸函数名**（如 `add`）。这带来三个问题：① 用户无法知道有哪些可用函数，易填错、易遗忘；② 函数标识不含插件名，无法区分不同插件中的同名函数；③ 随着插件（预置 + 用户自定义）不断演化，函数数量可能很大，手填不可维护。本变更把函数标识规范为**全名 `插件名.函数名`**（跨插件允许同名），并让编辑器**罗列全部可选函数 + 支持搜索**；同时把其他可能变大的下拉（ref 目标文档、槽位 / 分支子节点）升级为可搜索下拉。

## What Changes

**函数全名标识（BREAKING）**
- 函数标识 = **全名** `插件名.函数名`（如 `compute.add`）；行为树 FunctionCall 的 `function` 字段存全名。
- 注册表约束从「函数名全局唯一」放宽为「**同一插件内函数名唯一，跨插件允许同名**」（如 `compute.sort` 与 `mylib.sort` 共存）。
- 注册表键 / 查找 / 分发 / 解析校验 / 插件引用检测全部按全名；LLM 工具集工具名 = 全名（避免同名歧义）。
- 提供**一次性迁移脚本**：把已保存行为树中的裸函数名按插件归属改写为全名（本次验证后不再需要，新建树即全名）。

**函数清单 API**
- 新增 `GET /api/functions`：跨插件聚合返回 `[{full_name, plugin, name, description, returns, parameters}]`，供编辑器函数选择器与提示使用。

**编辑器可搜索下拉**
- 新增自研 `Combobox` 组件（输入过滤 + 键盘导航 + 点击选择；当前值不在选项中时也原样显示）。
- 函数名选择器：罗列全部函数全名（`compute.add`）+ 描述，支持前缀搜索（输入 `com` 过滤出 `compute.add` 等）。
- ref 目标文档、槽位 / Branch 子节点下拉升级为 Combobox（支持搜索）。
- 类型下拉（固定枚举）保持不变。

## Capabilities

### New Capabilities
- `tree-editor`: 编辑器可搜索下拉（函数名 / ref 目标文档 / 槽位 / 分支），自研 Combobox 组件。

### Modified Capabilities
- `plugin-system`: 函数全名标识（`插件名.函数名`）；同插件内函数名唯一、跨插件允许同名；分发 / 工具名按全名。
- `behavior-tree-parser`: FunctionCall 的 `function` 字段为全名标识。
- `orchestrator`: FunctionCall 执行与插件分发按全名。
- `plugin-management`: 新增 `GET /api/functions` 函数清单端点；插件 `functions` 字段返回全名；引用检测按全名。

## Impact

- **插件框架** `webops/plugin_system/`：`FunctionDef` 加 `plugin` / `full_name`；注册表键改全名、冲突检测改同插件内。
- **解析 / 编排** `webops/parser/`、`webops/orchestrator/`：按全名校验与分发。
- **后端** `webops/server/`：新增 `/api/functions`；插件服务返回 / 匹配全名。
- **前端** `webops/frontend/`：新增 Combobox 组件；函数名 / ref / 槽位下拉接入；treeModel 值改全名。
- **迁移**：一次性脚本改写 DB 中已保存行为树的裸函数名；同步更新测试、docs 示例、E2E 数据。
- **文档**：`docs/contract.md`（§4/§5/§12/§13）、`docs/specs/`、openspec 主 specs 同步。