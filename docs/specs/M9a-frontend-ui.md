# M9a · 前端 UI Spec

> 依据契约 `docs/contract.md` §12.3（引擎内嵌形态）、§12.4（前端执行报告实时展示）、§12.5（前端行为树复合节点视图）、§4.3（复合节点）、§5.8.3（报告）。
> **实现状态：已全部落地并通过前后端实机联调**（OpenSpec change `m9a-frontend-ui`）。

## 1. 概述

WebOps 的用户交互界面：行为树编辑器（拖拽节点 → 生成含复合节点的行为树文档）、行为树管理（CRUD）、执行报告页（轮询执行状态实时渲染节点进度与截图）。**纯前端，依赖 M9b 后端 API。**

## 2. 功能范围

| 功能 | 说明 | 契约依据 |
|---|---|---|
| 行为树编辑器 | 拖拽节点 + 填写信息 → 生成含复合节点的行为树文档 | §12.5/§4.3 |
| 行为树管理 | 列表/查看/修改/删除（CRUD） | §12.2-M9a |
| 执行报告页 | 轮询执行状态，实时渲染节点进度 + 截图 | §12.4/§5.8.3 |
| 复合节点视图 | 用户始终看到含复合节点的行为树（Step/Branch/LoopUntil/...） | §12.5 |
| 清晰度校验提示 | 保存时校验（M9b 复用 M2），友好提示用户修正 | §12.5 |

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

### 5.3 编辑器节点模型（复合节点，§4.3）

支持节点：Step / Branch / LoopUntil / IfThenElse / Retry / Sequence / ref 块引用。用户填写自然语言叶子内容（action/expect/when/until...）。

### 5.3.1 多块文档编辑器（方案 2，契约 §4.1）

编辑器按"块 = 声明 + 行为树"模型编辑文档：

- **块列表面板**（`BlockListPanel`）：列出主块（标「主」）+ 全部附属块；点击切换当前编辑块；「新建块」按钮创建附属块（prompt 输入块名）；附属块可删除（主块不可删）。
- **块模型**（`BlockDoc = { name, decl, tree }`）：`decl` 保存块声明（inputs/outputs/config，`BLOCK_DECL_KEYS = {inputs, outputs, timeout, retry, browser}`），`tree` 为可编辑的行为树（EditorNode）。
- **解析/序列化**：`parseDocument(yamlText)` → `{ mainBlock, blocks: BlockDoc[] }`（每块提取声明键与唯一行为树键）；`serializeDocument(blocks)` 重建多块文档（主块 + 附属块，保留各块声明）。`parseTree(yamlText, docName?)` 兼容：多块取主块（文档名匹配，无匹配取第一个）。
- **裸树兼容**：无 `block` 前缀的文档（整文档即根块）按主块加载/保存，保持原样。
- **保存**：当前编辑块树写回 `activeBlock`，整体 `serializeDocument` 输出（保留全部块与声明）。

**实现说明（已落地）**：

- 工程位置 `webops/frontend/`（Vite + React 18 + TS），目录按 `frontend-style.md`：`src/api|components|features|hooks|types`。
- 路由（react-router-dom）：`/` 列表、`/editor/:id?` 编辑器、`/runs/:runId` 报告页。
- 状态：`useState`（表单）+ `useReducer`（编辑器节点树 add/update/remove/move）+ `usePolling` hook（1 秒轮询，卸载清理）。
- 编辑器：内部维护复合节点树模型，`js-yaml` 双向转换（**不展开复合节点**，§12.5）；保存前先 `POST /check`，校验失败渲染错误清单阻止保存。
- **序列化格式（对齐契约 §4.1 顶层映射）**：`serializeTree` 统一以「节点键映射」输出——单节点 → `{Step: {...}}`，Sequence 根 → `{Sequence: [...]}`。**不直接 dump 数组**（顶层序列会被后端 M2 以「必须是 yaml 顶层映射」拒绝）。
- API 客户端集中于 `src/api/`（`request.ts` 封装，`/api` 前缀，snake_case 类型对齐后端 Pydantic）。
- 报告页：`usePolling` 轮询 `/api/runs/{run_id}/state`（shouldStop=finished），渲染进度条/当前节点/SUCCESS/FAILURE 着色 + 截图（经 `/api/reports/{path}`）。

**运行约定**（AGENTS.md 端口约束）：vite dev 固定端口 **5174**（`strictPort`，避开 NexusOps 的 5173），`vite.config.ts` 的 `/api` 代理 target 指向 `http://127.0.0.1:8001`（**禁用 8000/5173**）。一键启动：项目根 `dev-restart.ps1`。

## 6. 验收标准

- [x] 编辑器可拖拽节点、填写信息，生成合法行为树文档（含复合节点）
- [x] 行为树 CRUD 完整可用
- [x] 保存时触发校验，校验失败友好提示修正
- [x] 点击执行 → 触发 run → 1 秒轮询状态 → 实时渲染节点成功/失败 + 截图
- [x] 执行完毕后展示完整执行报告与回溯报告
- [x] 用户始终看到复合节点视图（引擎基础节点对用户不可见）

## 7. 测试策略

- **组件测试**：编辑器拖拽/表单、节点树渲染（`src/**/*.test.tsx`）——编辑器拖拽等复杂 UI 操作由组件测试覆盖
- **API mock 测试**：mock `src/api/`（vi.mock），覆盖列表/编辑/校验/轮询流程与 404 错误路径
- **轮询渲染测试**：fake timers 模拟执行状态序列，验证进度与截图实时更新
- **Playwright E2E**（`e2e/workflow.spec.ts` + `e2e/ref-call.spec.ts`，`npm run test:e2e`）：**前端执行行为树 + 前端查看执行结果**——列表页点「执行」→ 报告页轮询 → 切换查看完整执行报告/回溯报告。`ref-call.spec.ts` 覆盖**嵌套 ref 动态调用**（主块 ref 附属块、args 传参/returns 回收），验证块引用执行链路。E2E 用 API 预置行为树（不模拟编辑器拖拽），聚焦执行/轮询/报告渲染链路
- **实机联调**（已通过）：vite dev(5174) → uvicorn(8001) 代理链路，list/create/check/get/run/轮询/report/trace 全通

**测试结果**：`npm run lint` ✓、`npm run typecheck` ✓、`npm test` **74 passed**（13 文件）、`npm run test:e2e` **2 passed**（workflow + ref-call，Playwright，前端执行+报告查看链路）、`npm run build` ✓。