# qualified-function-names 设计

## 1. 函数全名标识（M3 插件框架）

- `FunctionDef`（`webops/plugin_system/defs.py`）增加 `plugin: str = ""` 字段；新增 `full_name` 属性 = `f"{plugin}.{name}" if plugin else name`。frozen dataclass，注册时用 `dataclasses.replace` 填充 `plugin`。
- **LLM 工具名转义**：多数 OpenAI 兼容 API 的工具名仅允许 `[a-zA-Z0-9_-]`，**点号会被拒绝**（实测 `compute.multiply` → LLMProtocolError）。故 `FunctionDef.tool_name` = `full_name.replace(".", "__")`；`to_tool_spec` 用 `tool_name` 作为工具名；M6 分发时按 `tool_name` 反查回 `full_name` 再 `registry.call`（跨插件同名工具仍不歧义）。行为树 `function` 字段始终存**全名**（带点号）。
- `PluginRegistry`（`webops/plugin_system/registry.py`）：
  - `register`：函数键 = `spec.full_name`；冲突检测改为「同插件内重名」——`f"{plugin.name}.{spec.name}"` 已存在 → 拒绝；跨插件同名（full 不同）自动不冲突；**同一插件重复注册视为重载（幂等覆盖）**（引擎每次 run 重载预置插件）。
  - `unregister`：键 = full。
  - `function(full)` / `owner(full)` / `call(full, ...)`：键 = full；`call` 定位插件后把**裸名** `spec.name` 传给 `plugin.call`。
  - `functions()` / `functions_of` / `loaded_functions`：键已含插件名，owner 映射不变。

## 2. 解析与运行时

- `parser/checks.py`：`registry.function(node.function)` 直接按全名查（键已是全名）；`unknown_function` 报错信息含全名。
- `orchestrator/traverser.py`：`registry.function(full)` / `registry.call(full, ...)`（键变全名，调用逻辑不变）。
- `leaf_agent/executor.py`：工具 schema 来自 `FunctionDef.to_tool_spec`（自动转义全名）；`_plugin_tool_call` 先按 LLM 工具名查注册表，未命中则按 `tool_name` 反查回全名再 `registry.call`。
- **浏览器懒启动**（修复后台任务 Playwright sync/async 冲突）：`Engine.run` 不再无条件 `browser.start()`；改为浏览器插件 `init` 时（懒装配）冷启动驱动（`runtime.browser_config` 传入）。纯计算行为树零浏览器开销，不再在后台线程触发 `sync_playwright`。

## 3. 插件服务与 API

- `server/services/plugins.py`：`_function_names` 返回 `s.full_name`；`_has_ref` / `_nullify_ref` 用 `_FUNCTION_LINE`（name 组已支持 `[\w.]*`）按全名匹配；`init_builtins` 刷新 `functions`（全名）。
- `server/schemas/plugin.py`：`PluginOut.functions` 为全名列表；新增 `FunctionInfo` schema（full_name / plugin / name / description / returns / parameters）。
- `server/routers/plugins.py` 或新 `routers/functions.py`：`GET /api/functions` 聚合 `registry.functions()` 返回 `FunctionInfo[]`（预置 + 自定义）。

## 4. 前端 Combobox 与选择器

- `components/Combobox.tsx`：受控组件 `{value, onChange, options: {value,label,description?}, placeholder}`；输入过滤（label 前缀 / 包含匹配）、↑↓ 选择、回车确认、Esc 关闭、失焦保持；**value 不在 options 时原样显示**（兼容旧树 / 手输）。
- `api/plugins.ts`（或新 `api/functions.ts`）：`listFunctions(): FunctionInfo[]` → GET `/api/functions`。
- `types/plugin.ts`：加 `FunctionInfo`。
- `PropertyPanel.tsx`：
  - 函数名：Combobox，options 来自 listFunctions（full_name + description），onChange 存 full_name。
  - ref 目标文档：Combobox（docNames）。
  - 槽位 / Branch：Combobox（slotOptions 的 nodeLabel）。
- `treeModel.ts`：`function` 值 = 全名（结构不变）。
- `NodeCard`：展示 full_name（已是 `node.function`）。
- `validation.ts`：保持非空校验。

## 5. 一次性迁移

- `scripts/migrate_function_names.py`：连接 SQLite DB，扫描 `trees.content`（yaml），提取 FunctionCall 的 `function` 值；按「当前插件清单（builtin + custom）」建裸名→全名映射（旧注册表裸名全局唯一，映射确定）；改写为全名并写回；输出变更报告（含未能映射的裸名）。
- 运行一次 + 真实验证（执行迁移后的行为树），验证后脚本不再需要。
- 同步更新测试 / E2E / docs 中的裸名用例。

## 6. 验证

- 后端：注册表同名 / 全名分发单测；全量 pytest + ruff。
- 前端：Combobox 组件测试 + functionCall.test.ts 全名；typecheck / lint / test。
- E2E：function-call.spec.ts 全名 + 实机验证迁移后的树。