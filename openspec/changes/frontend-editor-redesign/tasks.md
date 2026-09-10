## 1. 文档库与跨文档引用（阶段 1）

- [x] 1.1 新增 DB-backed `RefResolver`：按文档名从 DB 加载 `Tree.content` → 构造 `DocumentSource`，实现 `RefResolver` 接口（文档不存在抛 `RefNotFoundError`）。验证：单测覆盖"按名查到/查不到"。
- [x] 1.2 server 装配改用 DB-backed resolver 替换空 `MappingResolver`（engine.py / validation.py）。验证：`pytest tests/server -q` 通过。
- [x] 1.3 新增按文档名查 API（`GET /api/trees/by-name/{name}`，name 唯一约束）。验证：API 单测覆盖命中/404。
- [ ] 1.4 跨文档引用端到端：创建两个文档（A ref B），校验 A 通过、执行 A 成功（B 的 Root 被执行）。验证：集成测试 + `pytest -q` 全量通过。（待任务 3 执行器适配后完成）
- [ ] 1.5 文档同步：contract.md / M7 spec / openspec orchestrator 记录跨文档引用经文档库。验证：文档 grep 确认无旧"空 resolver"表述。

## 2. DSL 一文档一树（阶段 2）

- [x] 2.1 M2 parser 新增一文档一树解析（`tree`/`nodes`/`root` + 文档级 inputs/outputs + 全局配置保留名）：平铺节点定义、`slots` 引用、`root` 引用、节点 `id`/`name`/`type`。验证：新解析单测覆盖合法/非法文档。
- [x] 2.2 从 `root` 沿 `slots` 构建主树（基础节点，Root 起始）；游离节点保留为游离树。验证：单测断言主树结构与游离树集合。
- [x] 2.3 解析校验：单根（恰一个 type:Root 且 root 引用指向它）、主树与每棵游离树无环、slots 引用存在、节点必填字段（action/expect/max 等）、文档级声明合法。验证：校验单测覆盖各反例。
- [x] 2.4 ref 参数校验：args 数量/顺序/类型匹配被引文档 inputs（含**字面量**传入：非变量名则按 str/int/float/bool 解析并校验类型）；returns 数量匹配 outputs、键为本树新参数名且不重名、类型合法；目标文档存在（经 resolver）；**跨文档引用环检测**（A→B→A 直接/间接循环）。验证：校验单测覆盖参数对齐反例、字面量、跨文档环。
- [x] 2.5 迁移工具：**已废弃**——旧多块 DSL 完全移除（用户决策：不为兼容保留冗余），parser 重写为纯一文档一树，无需迁移工具；旧 parser 测试删除，新 DSL 测试建立（onedoc + onedoc_integration）。
- [ ] 2.6 文档同步：contract.md §4.1 / M2 spec / openspec behavior-tree-parser 同步一文档一树（含 `tree: <名>` 顶层键）。验证：文档 grep 确认无旧 `block`/多块表述（历史设计稿除外）。（随批次 L 完成）

> **阶段 2 完成（2026-09-10）**：一文档一树 DSL 解析（tree/nodes/root + slots + 校验 + ref 参数/跨文档环）已实现并测试；旧多块 DSL 与 parser 死代码完全废弃删除；全量 703 passed / 3 skipped，ruff 全绿。剩余：任务 3（执行器适配）、任务 4/5（前端重写）为后续阶段。

## 3. M7 执行器适配（阶段 2 收尾）

- [ ] 3.1 `_tick_ref` 改为按文档名加载被引文档树（经 resolver），从其 Root 执行；args/returns 语义不变。验证：执行集成测试覆盖多层引用（A→B→C）与引用不存在 FAILURE。
- [ ] 3.2 `blocks_tree` 语义从"块名→树"调整为"文档名→树"（或由 resolver 加载替代）。验证：现有执行器测试适配后全量通过。

## 4. 前端画布重写（阶段 3）

- [ ] 4.1 节点模型重构：`EditorNode` = `{id, type, name, 节点字段, slots}`；节点对象池状态；id 自动生成（n1/n2...）、导入保留。验证：model 单测覆盖节点创建/id 生成/序列化往返。
- [ ] 4.2 画布布局引擎：固定尺寸节点卡片、根在上向下生长、兄弟水平均布（自底向上算宽、自顶向下定位）；主树区 + 游离区自动布局；游离树顶部标签。验证：布局单测覆盖多层树/多棵游离树包围盒。
- [ ] 4.3 SVG 连线：父子 ortho 折线（连线在节点下层）。验证：渲染测试断言连线元素存在与坐标。
- [ ] 4.4 槽位 UI：容器节点属性面板（IfThenElse 固定 2 槽 + 条件字段；Sequence 可变槽 + 增删）；下拉只显示各棵游离树的根（游离树最上层节点/单节点自身），选中即整棵游离树挂入。验证：组件测试覆盖槽位下拉可选范围（不含已挂载/树内非根节点）、增删槽位、挂载/剥离迁移。
- [ ] 4.5 删除/修改语义：删槽位=解引用回游离区；删单节点=子节点各自成游离树；删子树=连带删；改槽位=旧节点回游离区。验证：model 单测覆盖删除/修改矩阵各场景。
- [ ] 4.6 ref 参数编辑：下拉选目标文档 → 自动加载其 inputs/outputs → args/returns 表单（列表/字典）；编辑时即时校验（对齐/变量存在/命名冲突/类型匹配/字面量）；**选目标文档时即时检测跨文档引用环并拒绝**。验证：组件测试 + 后端 API mock 覆盖加载、校验与环拦截。
- [ ] 4.7 ref 展开/收缩：展开显示被引文档只读子树（懒加载逐层）；收缩连同子引用一并收起。验证：组件测试覆盖展开/收缩与懒加载。
- [ ] 4.8 即时校验 + 保存汇总：必填字段红框标记；保存时后端 `/check` 权威兜底。验证：组件测试覆盖红框提示与保存校验流程。
- [ ] 4.9 节点卡片视觉：固定尺寸、类型图标/颜色区分、显示 name。验证：组件/渲染测试。
- [ ] 4.10 移除 BlockListPanel（无附属块）；根节点（type:Root）固定呈现。验证：组件测试断言无块列表、根节点存在。

## 5. 前端 DSL 序列化与文档加载

- [ ] 5.1 前端解析/序列化新 DSL（`tree`/`nodes`/`root` + 文档级声明/配置 + 节点 id/name/type/slots/ref 参数），往返无损。验证：yaml 单测覆盖解析→序列化→再解析一致（含 ref 参数，修复旧数据丢失缺陷）。
- [ ] 5.2 前端按名加载被引文档（by-name API）用于 ref 展开与参数加载。验证：API mock 测试。
- [ ] 5.3 文档导入（md/yaml → 创建行为树，保留原 id）。验证：导入集成测试 + 前端流程。

## 6. 集成与回归

- [ ] 6.1 全量后端 `pytest -q` 通过（含迁移工具/新 DSL/执行器适配）。
- [ ] 6.2 前端 `npm test` / lint / typecheck 通过。
- [ ] 6.3 E2E：前端创建多文档（A ref B 嵌套），执行并查看报告符合预期（真实浏览器 + 真实 LLM）。验证：`npm run test:e2e`。
- [ ] 6.4 文档全量同步：contract.md / 各模块 spec / openspec specs（frontend-editor、behavior-tree-parser、orchestrator）与实现一致。验证：文档与代码交叉核查。