## 任务

### 组1：插件框架全名标识（M3）
- [x] T1 FunctionDef 加 plugin/full_name，to_tool_spec 用全名
- [x] T2 注册表 register 键改全名、同插件内重名拒绝、跨插件同名允许
- [x] T3 注册表 function/owner/call/unregister/functions_of/loaded_functions 按全名
- [x] T4 单测：跨插件同名共存、同插件重名拒绝、全名分发

### 组2：解析与运行时
- [x] T5 parser/checks.py 按全名校验（报错含全名）
- [x] T6 orchestrator/traverser.py 全名分发
- [x] T7 单测：解析 / 执行全名用例

### 组3：插件服务与 API
- [x] T8 PluginOut.functions 返回全名；_function_names 用 full_name
- [x] T9 GET /api/functions 端点 + FunctionInfo schema
- [x] T10 引用检测（_has_ref / _nullify_ref）按全名
- [x] T11 单测：函数清单端点、引用检测

### 组4：前端
- [x] T12 Combobox 组件 + 样式 + 组件测试
- [x] T13 api/plugins.ts + types/plugin.ts 函数清单
- [x] T14 函数名选择器接入 /api/functions（搜索 + 描述）
- [x] T15 ref 目标文档、槽位 / Branch 下拉 → Combobox
- [x] T16 treeModel / NodeCard / validation 适配全名
- [x] T17 组件测试更新（functionCall.test.ts 全名）

### 组5：迁移
- [x] T18 迁移脚本 scripts/migrate_function_names.py
- [x] T19 迁移脚本单测（含映射 / 未知名处理）
- [x] T20 更新后端测试裸名用例（parser / leaf_agent / plugin_system / orchestrator）
- [x] T21 更新 E2E（function-call.spec.ts / plugins.spec.ts）+ 前端测试
- [x] T22 实跑迁移 + 执行迁移后行为树验证

### 组6：文档
- [x] T23 docs/contract.md（§4/§5/§12/§13）+ docs/specs 全名
- [ ] T24 同步 openspec 主 specs + 验证（归档时执行）

### 组7：回归
- [x] T25 全量 pytest + ruff；前端 typecheck/lint/test；E2E 全绿
  - 后端 619 单测 + 101 集成全过，ruff 全绿；前端 138 测试 + typecheck/lint 全过
  - E2E：function-call（F1/F2/F3/C1/F5）5/5、plugins（P1–P5）5/5 全绿
  - 迁移脚本实跑（裸名→全名）并执行迁移后树验证（compute.add/multiply → 5/20）
  - 修复：LLM 工具名点号被拒（tool_name 转义）；浏览器懒启动（后台任务 Playwright 冲突）