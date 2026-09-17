> **模块重编号**：原 **M9a 前端 UI** 重编号为 **M9**。新增插件管理页（CodeMirror 6）。

# M9a · 前端 UI Spec

> 依据契约 `docs/contract.md` §12.3（引擎内嵌形态）、§12.4（前端执行报告实时展示）、§12.5（前端行为树复合节点视图）、§4.3（复合节点）、§5.8.3（报告）。
> **实现状态**：行为树管理/执行报告链路已落地并通过前后端实机联调（OpenSpec change `m9a-frontend-ui`）；编辑器按 `frontend-editor-redesign`（节点画布 + 槽位引用 + 一文档一树）重设计，见 §5.3.1。

## 1. 概述

AutoBranch 的用户交互界面：行为树编辑器（拖拽节点 → 生成含复合节点的行为树文档）、行为树管理（CRUD）、执行报告页（轮询执行状态实时渲染节点进度与截图）、**插件管理页（新增/编辑/删除自定义插件）**。**纯前端，依赖 M9b 后端 API。**

## 2. 功能范围

| 功能 | 说明 | 契约依据 |
|---|---|---|
| 行为树编辑器 | 拖拽节点 + 填写信息 → 生成含复合节点的行为树文档 | §12.5/§4.3 |
| FunctionCall 节点编辑 | 编辑器支持 `type: FunctionCall` 节点（函数名 + args + returns 编辑，属性面板与 ref 对称） | §12.2.1 |
| 可搜索下拉 | 函数名选择器（罗列全名 `插件.函数` + 描述，支持过滤）、ref 目标文档、槽位/分支子节点下拉均支持输入过滤（类型下拉保持原生 select） | §12.2.1 / tree-editor spec |
| 行为树管理 | 列表/查看/修改/删除（CRUD） | §12.2-M9a |
| 执行报告页 | 轮询执行状态，实时渲染节点进度 + 截图 | §12.4/§5.8.3 |
| 复合节点视图 | 用户始终看到含复合节点的行为树（Step/Branch/LoopUntil/...） | §12.5 |
| 清晰度校验提示 | 保存时校验（M9b 复用 M2），友好提示用户修正 | §12.5 |
| 插件管理页 | 插件列表（预置/自定义徽标）+ 新增/编辑（CodeMirror 6 编辑器）+ 保存校验（行号/约束提示）+ 删除关联弹窗（引用置空确认） | plugin-management spec |

**非目标（第一版）**：不做实时 WebSocket 推送（采用 1 秒轮询，§12.4）。

## 3. 数据依赖

### 3.1 输入
- **行为树文档**（yaml/dict）：编辑器产出，含复合节点
- **M9b API 响应**：CRUD 结果、校验报告、执行状态、报告/截图

### 3.2 输出
- **行为树文档**：保存到 M9b
- **执行触发请求**：点击执行 → M9b 执行接口
- **执行状态轮询请求**：定时查询

## 4. 单元间依赖

- **依赖**：M9b（后端 API）
- **被依赖**：无（最上层）

## 5. 接口契约（消费 M9b API）

### 5.1 行为树管理 API

```
GET    /api/trees              # 列表
POST   /api/trees              # 创建
GET    /api/trees/by-name/{name}  # 按文档名查（ref 展开/参数加载）
GET    /api/trees/{id}         # 查看
PUT    /api/trees/{id}         # 修改
DELETE /api/trees/{id}         # 删除
POST   /api/trees/{id}/check   # 清晰度校验
```

### 5.2 执行 API

```
POST   /api/trees/{id}/run     # 触发执行 → run_id
GET    /api/runs/{run_id}/state   # 轮询执行状态（进度/当前节点/已完成报告）
GET    /api/runs/{run_id}/report  # 执行报告
GET    /api/runs/{run_id}/trace   # 回溯报告
GET    /api/reports/{path}     # 截图/报告文件
```

### 5.3 编辑器节点模型（一文档一树，§4.1）

支持节点：`Action / Root / Step / Sequence / IfThenElse / Branch / Retry / LoopUntil / ref`（ref = 文档引用）。`Action` 为真正叶子（`fields.description` = 自然语言操作描述）；`Step` 经 `action` 槽位挂操作子树、`expect` 为验证条件字段；用户填写自然语言叶子内容（description/expect/when/until...）。

### 5.3.1 节点画布编辑器（一文档一树）

编辑器以"真实画布节点 + 节点对象池 + 槽位引用"编辑一份一文档一树文档：

- **画布呈现**：每个节点为固定尺寸卡片，类型用颜色/形状/图标区分，显示用户自定义 `name`；树从根节点在上、向下生长，兄弟水平排布，父子以连线绘制；节点位置自适应布局，不需手动摆放。画布分**主树区**（`root` 沿槽位引用递归可达）与**游离区**（与 Root 不联通的游离树，顶部带根 name + 「游离」标记）。
- **节点对象池 + 统一槽位**：全部节点独立定义在 `nodes` 下，节点间一切动作关联经**语义命名字段**引用子树根 id：`Root.body`、`Sequence.actions`（有序列表）、`Step.action`、`IfThenElse.then`/`else`、`Branch.action` + `branches[].action`（每分支一行）、`Retry.body`、`LoopUntil.action`；槽位下拉只展示各棵游离树的根（已挂载节点/树内非根节点不展示）。`Sequence.actions` 可增删；`IfThenElse` 的 `then`/`else` 各 1 个槽；`Branch` 可增删分支行。条件（`expect`/`if`/`when`/`until`）与 `description`/`max` 等为标量字段（存于 `fields`），不占槽位。
- **根节点**：每文档恰一个 `type: Root`（固定 1 槽 `body`），不可删除/替换；`root` 顶层键引用它。
- **Action 叶子**：真正叶子节点，无槽位，仅 `fields.description`（自然语言操作描述），可被任意槽位挂载；创建 Step 时自动附带一个 Action 子节点挂入其 `action` 槽位（`createStepWithAction`）。
- **文档接口编辑**：属性面板顶部常驻「文档接口」区（`DocInterfaceEditor`）——编辑树 `inputs`（名→类型，类型 str/int/float/bool/page_ref）与 `outputs`（名列表），可增删改；ref 参数对齐依据该声明。只读模式（ref 预览）下禁用。
- **ref 参数编辑**：ref 节点下拉选目标文档 → 自动加载其 `inputs`/`outputs` 生成参数表单；入参 `args` 为列表（按序对应 inputs，值优先匹配本树已有变量名，未命中作字面量）；出参 `returns` 为字典（键=本树新建接收名，值=类型，按序对应 outputs）；编辑时即时校验对齐/命名冲突/类型，并即时检测跨文档引用环。目标未选/加载中给出提示。
- **ref 展开/收缩**：收缩态为单节点占位（显示目标文档名）；展开态将**被引文档整树并入主树布局**（`layoutDocument` 的 `refExpansions`，节点以 `<refId>:` 前缀隔离，向下生长不遮挡主树），与主树以连线相连、预览内部父子连线一并渲染；逐层懒加载，收缩连同已展开子引用一并收起。展开/收缩按钮位于 ref 节点卡片右上角。**预览节点可点击查看只读属性面板**（展示节点字段/槽位/ref 参数，禁止编辑）。
- **删除/修改语义**：删槽位=解引用（子节点回游离区）；删单节点=各槽位子节点各自成游离树；删子树=连带后代；改槽位=旧节点回游离区、新节点入主树；删 ref 仅解除引用，被引用文档不受影响。删除/删除子树操作位于**属性面板**（节点卡片上不提供，避免重复）。
- **即时校验**：节点必填字段（Action `description`、Step `action` 槽位+`expect`、IfThenElse `if`+`then`+`else`、Branch `action`+至少一分支、LoopUntil `until`+`action`+`max`、Retry `body`+`max`、ref `target`）红框标记；保存时汇总校验（单根、主树与各游离树无环、槽位引用存在且无重复引用、ref 目标存在）并经后端 `/check` 权威兜底。
- **节点标识**：`id` 文档内唯一（自动生成 n1/n2...、**文档导入保留原 id**，仅 `[A-Za-z0-9_-]`、≤64）；`name` 用户自定义画布显示名（≤64，不强制唯一，空则显示类型名）。

**实现说明（已落地）**：

- 工程位置 `autobranch/frontend/`（Vite + React 18 + TS），目录按 `frontend-style.md`：`src/api|components|features|hooks|types`。
- 路由（react-router-dom）：`/` 列表、`/editor/:id?` 编辑器、`/runs/:runId` 报告页。
- **节点模型**（`features/tree-editor/treeModel.ts`）：`TreeNode = {id, type, name, fields, body?, actions?, action?, then?, else?, branches?, target?, args?, returns?}`（`fields` 存 `description`/`expect`/`if`/`when`/`until`/`max` 等标量字段；槽位字段按类型出现：`body`/`actions`/`action`/`then`/`else`/`branches`；`target`/`args`/`returns` 仅 `ref`）、`TreeDoc = {tree, inputs, outputs, config, nodes, root}`；`parseDoc`/`serializeDoc` 与一文档一树 DSL 无损往返（含 ref args/returns）；`nextNodeId`/`freeRoots`/`referencedIds` 支撑 id 生成、游离判定与重复引用校验。
- **布局引擎**（`features/tree-editor/layout.ts`）：固定尺寸卡片，自底向上算宽、自顶向下定位（根在上、向下生长、兄弟水平均布）；`layoutDocument` 主树在左上、游离树依次排布其下。
- 状态：`useState`（表单）+ `useReducer`（编辑器节点树）+ `usePolling` hook（1 秒轮询，卸载清理）。
- 保存前先 `POST /check`，校验失败渲染错误清单阻止保存；`js-yaml` 双向转换（**不展开复合节点**，§12.5）。
- API 客户端集中于 `src/api/`（`request.ts` 封装，`/api` 前缀，snake_case 类型对齐后端 Pydantic）。
- 报告页：`usePolling` 轮询 `/api/runs/{run_id}/state`（shouldStop=finished），渲染进度条/当前节点/SUCCESS/FAILURE 着色 + 截图（经 `/api/reports/{path}`）。

**运行约定**（AGENTS.md 端口约束）：vite dev 固定端口 **5174**（`strictPort`，避开 NexusOps 的 5173），`vite.config.ts` 的 `/api` 代理 target 指向 `http://127.0.0.1:8001`（**禁用 8000/5173**）。一键启动：项目根 `dev-restart.ps1`。

## 6. 验收标准

> 编辑器画布重写（节点对象池/槽位/主树区+游离区/ref 展开）按 OpenSpec change `frontend-editor-redesign` 推进；节点模型（`treeModel.ts`）与布局引擎（`layout.ts`）已落地，画布交互项待完成。

- [ ] 画布自动布局：根在上、向下生长、兄弟水平均布；主树区 + 游离区独立呈现（游离树带标记）
- [ ] 节点对象池 + 统一槽位：语义命名字段（body/actions/action/then/else/branches）槽位下拉只列游离树根，Sequence.actions/Branch.branches 增删、挂载/剥离迁移正确；Action 叶子可被任意槽位挂载
- [ ] 每文档恰一 Root 节点且不可删除；游离树可保存（草稿）
- [ ] ref 参数编辑（选目标文档自动加载 inputs/outputs、args/returns 表单）与展开/收缩（只读预览）
- [ ] 删除/修改语义明确：删槽位=解引用回游离区；删单节点=子节点各自成游离树；删子树=连带后代
- [x] 行为树 CRUD 完整可用；保存时触发校验，校验失败友好提示修正
- [x] 点击执行 → 触发 run → 1 秒轮询状态 → 实时渲染节点成功/失败 + 截图；执行完毕展示完整执行报告与回溯报告
- [x] 用户始终看到复合节点视图（引擎基础节点对用户不可见）

## 7. 测试策略

- **组件测试**：编辑器拖拽/表单、节点树渲染（`src/**/*.test.tsx`）——编辑器拖拽等复杂 UI 操作由组件测试覆盖
- **API mock 测试**：mock `src/api/`（vi.mock），覆盖列表/编辑/校验/轮询流程与 404 错误路径
- **轮询渲染测试**：fake timers 模拟执行状态序列，验证进度与截图实时更新
- **Playwright E2E**（`e2e/workflow.spec.ts` + `e2e/ref-call.spec.ts`，`npm run test:e2e`）：**前端执行行为树 + 前端查看执行结果**——列表页点「执行」→ 报告页轮询 → 切换查看完整执行报告/回溯报告。`ref-call.spec.ts` 覆盖**跨文档 ref 动态调用**（文档 A `ref` 文档 B，args 传参/returns 回收），验证文档引用执行链路。E2E 用 API 预置行为树（不模拟编辑器拖拽），聚焦执行/轮询/报告渲染链路
- **实机联调**（已通过）：vite dev(5174) → uvicorn(8001) 代理链路，list/create/check/get/run/轮询/report/trace 全通

**测试结果**：`npm run lint` ✓、`npm run typecheck` ✓、`npm test` ✓、`npm run test:e2e` ✓（workflow + ref-call，Playwright，前端执行+报告查看链路）、`npm run build` ✓。