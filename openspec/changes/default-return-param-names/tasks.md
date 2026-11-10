# default-return-param-names 任务

## 1. 后端：类型化返回声明与 ASCII 规范

- [x] 1.1 `FunctionDef.returns` 改为 `{名称: 类型}`；`@engine_function`/`@llm_function` 接收映射；定义名/类型合法性校验
- [x] 1.2 注册表注册时校验 returns 名称 ASCII + 类型合法；非法抛 `PluginError`；旧式名字元组拒绝
- [x] 1.3 内置插件 compute/browser/file/ssh 全部补类型
- [x] 1.4 文档 `outputs` 改为 `{名称: 类型}`；parser/onedoc/models/orchestrator/context/engine/traverser 适配
- [x] 1.5 节点 id / inputs 键 / outputs 键 ASCII 校验；`tree` 与节点 `name` 不限制
- [x] 1.6 `FunctionInfo` / `/api/functions` 返回带类型 returns；前端类型同步

## 2. 后端：默认接收名归一化

- [x] 2.1 新增归一化服务：按来源返回声明顺序补名、类型来自来源、数量截断/补齐
- [x] 2.2 自动名冲突追加 `_1/_2`；冲突变量删除不回退；手工名不改写
- [x] 2.3 不自动改写 `Param.<旧名>` 引用；保存校验负责发现未定义引用
- [x] 2.4 归一化服务接入草稿命令、保存、迁移、运行前兜底

## 3. 后端：草稿/正式状态与命令式编辑

- [x] 3.1 `Tree` 增加 `status` 列（默认 published）+ 迁移；历史记录置 published
- [x] 3.2 新建草稿 API：临时名 `未命名-<时间戳>` + 空树，status=draft
- [x] 3.3 命令 API：add_node / delete_node / update_node / update_doc；后端生成节点 id、实现 Step 自动 Action、删除/槽位语义
- [x] 3.4 命令执行后将 published 置 draft；返回完整文档
- [x] 3.5 保存 API：完整校验 + 改名 + status=published；失败 422 保持 draft
- [x] 3.6 执行 API：draft 拒绝；列表/详情返回 status
- [x] 3.7 ref resolver/校验：目标必须 published，draft 目标报错

## 4. 历史数据迁移

- [x] 4.1 迁移脚本：节点 id/inputs/outputs/returns ASCII 改名 + 本树引用改写
- [x] 4.2 outputs 类型推断（NewParam/Define/来源节点），推断不出用 object
- [x] 4.3 补默认接收名/类型；迁移后状态 published
- [x] 4.4 清空 experiences
- [x] 4.5 `runs.content_snapshot` 不迁移

## 5. 前端：后端权威文档与草稿 UI

- [x] 5.1 列表显示草稿/正式状态；draft 不显示执行
- [x] 5.2 新建行为树调用“新建草稿”并进入编辑器；临时名显示
- [x] 5.3 编辑器改为命令 API：添加/删除/更新节点/文档接口均调用后端并应用返回文档
- [x] 5.4 文本输入 debounce/onBlur；草稿允许即时校验失败
- [x] 5.5 属性面板去除类型下拉；名称输入提交后端；类型只读展示
- [x] 5.6 保存调用 save API；保存成功回列表
- [x] 5.7 删除草稿/正式版统一删除记录

## 6. 文档与验收

- [x] 6.1 更新 `docs/contract.md`、`docs/specs/M1/M3/M7/M8/M9`、`docs/user-guide.md`、`README.md`
- [x] 6.2 后端 pytest（parser/plugin/registry/server/归一化/迁移/ref draft）
- [x] 6.3 前端 vitest（草稿标识、默认名只读类型、命令驱动编辑）
- [x] 6.4 Playwright E2E：新建草稿→编辑→保存→执行；草稿不可执行；ref draft 报错
- [x] 6.5 `ruff`、`pytest`、前端 typecheck/lint/test、`npm run test:e2e`
- [x] 6.6 按 AGENTS.md 提交推送（中文）
