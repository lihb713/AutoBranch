# frontend-editor-redesign 实施任务

> **2026-09-11 统一槽位模型 v2（用户批准）**：行为树节点只保留核心语义，节点间一切动作关联经**语义命名槽位字段**引用子树根 id；新增 **Action 叶子**；**Condition 为概念性节点**内嵌为字段。取代"仅 Root/Sequence 用 slots、其余字段型"的旧一文档一树版本。设计见 `docs/superpowers/specs/2026-09-11-unified-slot-model-design.md`。
> 槽位字段：Root.body / Sequence.actions / Step.action / IfThenElse.then+else / Branch.action+branches[].action / Retry.body / LoopUntil.action。条件字段：Step.expect / IfThenElse.if / Branch.branches[].when / LoopUntil.until。

## 1. 文档库与跨文档引用（阶段 1，已完成）

- [x] 1.1 新增 DB-backed `RefResolver`：按文档名从 DB 加载 `Tree.content` → 构造 `DocumentSource`，实现 `RefResolver` 接口（文档不存在抛 `RefNotFoundError`）。
- [x] 1.2 server 装配改用 DB-backed resolver 替换空 `MappingResolver`（engine.py / validation.py）。
- [x] 1.3 新增按文档名查 API（`GET /api/trees/by-name/{name}`，name 唯一约束）。
- [x] 1.4 跨文档引用端到端：创建两个文档（A ref B），校验 A 通过、执行 A 成功（B 的 Root 被执行）。
- [x] 1.5 文档同步：contract.md / M7 spec / openspec orchestrator 记录跨文档引用经文档库（批次 L 完成）。

## 2. DSL 统一槽位模型（阶段 2，重写）

- [x] 2.1 M2 parser 重写一文档一树 + 统一槽位：节点类型（Action/Step/Root/Sequence/IfThenElse/Branch/Retry/LoopUntil/ref），槽位字段按类型（Root.body/Sequence.actions/Step.action/IfThenElse.then+else/Branch.action+branches[].action/Retry.body/LoopUntil.action），Condition 概念字段（expect/if/when/until）。验证：解析单测覆盖各类型合法/非法文档。
- [x] 2.2 从 root 沿槽位字段构建主树；游离判定=未被任何槽位字段引用的节点为游离根。验证：单测断言主树结构与游离树集合。
- [x] 2.3 校验：单根（恰一个 type:Root 且 root 指向它）、槽位引用存在、无重复引用、主树与各游离树无环、必填字段（Action.description / Step.action+expect / IfThenElse.if+then+else / Branch.action+至少一个分支 / Retry.body+max / LoopUntil.until+action+max / ref.target）。验证：校验单测覆盖各反例。
- [x] 2.4 ref 参数校验：args 数量/顺序/类型匹配被引树 inputs（含字面量传入）；returns 数量匹配 outputs、键为本树新参数名且不重名、类型合法；目标文档存在（经 resolver）；跨文档引用环检测。验证：校验单测覆盖反例、字面量、跨文档环。
- [x] 2.5 M5 expand 展开适配槽位子树：Step→Sequence(Action+Condition)、Branch→Action+Selector、IfThenElse→Selector、Retry/LoopUntil→Repeat（循环体为槽位子树）。验证：展开单测。
- [x] 2.6 M7 executor 遍历适配统一槽位：Branch 先执行 action 子树再按序分流、Step 执行 action 子树并验证 expect、Action 叶子执行 description、Retry/LoopUntil 循环、IfThenElse 直接判 if 分流。验证：执行集成测试（多层、失败传播、循环安全闸）。
- [x] 2.7 旧 DSL 完全移除（字段型 then/else/body 目标字符串、统一 `slots` 键、旧 branch 分支行），parser/模型重写，旧测试更新/删除。验证：全量 `pytest -q` 通过。

## 3. M7 执行器跨文档适配（已完成，保留）

- [x] 3.1 `_tick_ref` 按文档名加载被引文档 Root 执行（args/returns 按序 zip，不变）。
- [x] 3.2 `blocks_tree` 语义"文档名→树"（不变）。

## 4. 前端画布重写（阶段 3）

- [x] 4.1 treeModel 重写统一槽位：TreeNode 槽位字段按类型（body/actions/action/then/else/branches…）、Action 叶子（description）、ref 参数（target/args/returns）；id 自动生成/导入保留；删除/修改语义（删槽位=解引用回游离区、删单节点=槽位子树各自成游离树、删子树=连带删、改槽位=旧子树回游离）。验证：model 单测覆盖创建/id/序列化往返/删除修改矩阵。
- [x] 4.2 布局引擎适配统一挂载点（`slotFields(node)` 抽象：布局、游离判定、连线基于它）。验证：布局单测覆盖多层树/多棵游离树包围盒。
- [x] 4.3 SVG 连线 + 节点卡片（Action/容器/ref 类型图标颜色区分、显示 name）。验证：渲染测试断言连线元素与卡片。
- [x] 4.4 槽位 UI：属性面板（挂载点下拉只显示各棵游离树根、Sequence actions 增删、Branch branches 编辑、创建 Step 自动附带 Action 挂入其 action 槽位）。验证：组件测试覆盖下拉可选范围、增删槽位、挂载/剥离迁移、Step 自动附 Action。
- [x] 4.5 ref 参数编辑：下拉选目标文档 → by-name 加载其 inputs/outputs → args/returns 表单；编辑时即时校验（对齐/变量存在/命名冲突/类型匹配/字面量）；选目标文档时即时检测跨文档环并拒绝。验证：组件测试 + API mock 覆盖加载、校验与环拦截。
- [x] 4.6 ref 展开/收缩：展开显示被引文档只读子树（懒加载逐层）；收缩连同子引用一并收起。验证：组件测试覆盖展开/收缩与懒加载。
- [x] 4.7 即时校验 + 保存汇总：必填字段/空槽位红框标记；保存时后端 `/check` 权威兜底。验证：组件测试覆盖红框提示与保存校验流程。
- [x] 4.8 TreeEditorPage 重写：主树区 + 游离区、根节点（type:Root）固定呈现、移除 BlockListPanel。验证：组件测试断言无块列表、根节点存在。

## 5. 前端 DSL 序列化与文档加载

- [x] 5.1 前端 parseDoc/serializeDoc 统一槽位 DSL（tree/nodes/root + 各类型槽位字段 + ref 参数 + branches），往返无损。验证：yaml 单测覆盖解析→序列化→再解析一致。
- [x] 5.2 前端按名加载被引文档（by-name API，api 层已完成）用于 ref 展开与参数加载。验证：API mock 测试。
- [x] 5.3 文档导入（md/yaml → 创建行为树，保留原 id）。验证：导入集成测试 + 前端流程。

## 6. 集成与回归

- [x] 6.1 全量后端 `pytest -q` 通过（含统一槽位 parser/展开/执行器）。
- [x] 6.2 前端 `npm test` / lint / typecheck 通过。
- [x] 6.3 E2E：前端创建多文档（A ref B），执行并查看报告符合预期（真实浏览器 + 真实 LLM）。验证：`npm run test:e2e`。
- [x] 6.4 文档全量同步：contract.md / 各模块 spec / openspec specs（frontend-editor、behavior-tree-parser、orchestrator）与实现一致。验证：文档与代码交叉核查。