## Context

动机见 proposal.md - Why。当前 WebOps 已具备引擎与后端 API 契约（`docs/specs/M9b-management-backend.md`），但无任何前端代码。M9a 是纯前端（React 18 + TypeScript + Vite），仅消费 M9b API，是最上层模块、无下游依赖。约束来源：

- 契约 §12.4：执行报告用**1 秒轮询**，非 WebSocket；§12.5：用户始终看到复合节点、前端不展开复合节点，清晰度校验"前端保存时校验一次 + 后端执行前再校验一次"
- `.opencode/rules/frontend-style.md`：目录约定（`src/api|components|features|hooks|types`）、就近状态管理、reducer 管理编辑器节点树、`usePolling` hook、列表 key 用稳定 id、组件不直接 fetch
- `.opencode/rules/api-conventions.md`：响应不包装、字段 snake_case、错误用 HTTP 状态码

## Goals / Non-Goals

**Goals:**
- 建立独立可运行的 Vite 前端工程，结构与 `frontend-style.md` 目录约定一致
- 拖拽式编辑器产出含复合节点的 yaml 文本，**前端不展开复合节点**，生成/校验交给后端
- 所有后端调用集中在 `src/api/`，类型与 M9b 的 Pydantic schema 一一对齐（snake_case）
- 轮询用可清理的通用 hook，卸载即停，避免内存泄漏与幽灵请求
- 组件测试 + API mock 测试 + 轮询渲染测试三层次覆盖，且可配合 M9b mock server 独立验收

**Non-Goals:**
- 不做 WebSocket/SSE 实时推送（契约 §12.4 明确第一版轮询）
- 不在前端实现清晰度校验逻辑或复合节点展开（M2/M9b 职责）
- 不引入 Redux 等重型状态库（规模不需要）
- 不实现用户登录鉴权等跨模块能力（M9b 契约中亦未包含）

## Decisions

### D1：工程骨架与目录结构

按 `frontend-style.md` 第 1 节落地 `webops/frontend/`：`src/api/`（API 客户端）、`src/types/`（领域类型）、`src/hooks/`（usePolling）、`src/components/`（通用无状态组件）、`src/features/tree-editor|runs|reports/`（页面级业务模块）。测试文件与组件同目录（`*.test.tsx`）。

- **备选**：按功能把 API 调用散在页面里 —— 违背规范"组件不直接 fetch"，拒绝
- **理由**：规范即约定，目录即边界，便于独立验收

### D2：路由采用 react-router-dom

编辑器、树列表、执行报告是三张独立页面，用 `react-router-dom` 组织路由（如 `/` 列表、`/editor/:id?`、`/runs/:runId`）。

- **备选**：手写页面级状态切换 —— 路由深链（刷新后直接回到报告页）无法表达，拒绝
- **理由**：URL 即状态，支持刷新/分享深链；单一事实来源

### D3：状态管理分层

- 组件内 UI 状态（表单、弹窗、折叠）：`useState`
- 编辑器节点树：`useReducer`（action：addNode/updateNode/removeNode/moveNode），派生值用 `useMemo`
- 跨页面共享（如选中的树）：最小化，用 React Context，不引入 Redux

- **备选**：Redux/Zustand —— 该规模下加重心智负担，`frontend-style.md` 明确不推荐
- **理由**：就近原则，状态贴近使用组件；节点树的增删改是复合更新，reducer 语义清晰

### D4：轮询抽为通用 `usePolling` hook

按 `frontend-style.md` §3.3 实现 `usePolling<T>(fetcher, shouldStop, intervalMs=1000)`：首次立即执行、按间隔 tick、`shouldStop` 为真即停、卸载清理 timer 与 cancelled 标志。执行报告页用它轮询 `/api/runs/{run_id}/state`，`shouldStop = state.finished`。

- **备选**：页面内裸写 `setInterval` —— 卸载不清理会造成幽灵请求，且多页面复用需要复制
- **理由**：契约 §12.4 固定 1 秒轮询；hook 化后行为一致、可测（fake timers）

### D5：编辑器产出 yaml 文本，不展开复合节点

编辑器内部维护复合节点树（前端模型），保存时用 `js-yaml` 序列化为行为树文档文本，原样交给后端校验/保存；加载时把后端返回的文档文本解析回树模型。**前端不做清晰度校验、不展开复合节点**（契约 §12.5），展开与校验是 M2/M9b 职责。

- **备选**：前端自行展开复合节点为基础节点再序列化 —— 直接违背 §12.5"用户始终看到复合节点"，拒绝
- **备选**：手写 yaml 拼接 —— 转义/缩进易错，`js-yaml` 成熟可靠
- **理由**：书写视图与执行视图分离，前后端各守边界，校验兜底在后端

### D6：保存时校验前置

保存/更新前先调 `POST /api/trees/{id}/check`；返回校验清单时阻止保存并渲染可读错误清单；通过才提交 CRUD 保存。与契约 §12.5"前端保存时校验一次（友好提示用户修正）"一致。

- **备选**：直接保存靠后端 422 报错 —— 错误时机晚、打断编辑流；前置校验更贴近编辑器内修正
- **理由**：校验逻辑完全复用 M9b（M2），前端只负责展示与引导修正

### D7：测试分层

- **组件测试**（Vitest + React Testing Library）：编辑器拖拽/表单/节点树渲染、复合节点视图只展示复合节点
- **API mock 测试**：mock `src/api/` 请求（如 vi.mock 或 MSW），覆盖列表/编辑/校验/删除流程与 404 等错误路径
- **轮询渲染测试**：用 fake timers 模拟执行状态序列，断言进度/着色/截图随状态更新、`finished` 后停止请求
- **集成验收**：配合 M9b 或 mock server 实际运行前后端

- **备选**：只用组件测试 —— 覆盖不到"轮询 1 秒时序"这一核心行为，拒绝
- **理由**：三种形态分别对应 spec 的三类可测试场景（`specs/frontend-ui/spec.md`）

## Risks / Trade-offs

- [1 秒轮询存在固有延迟与请求频率] → 节点粒度（秒级）下接近实时，契约 §12.4 已明确接受；失败可被下一次轮询捕获；后续可平滑升级 WebSocket（非目标）
- [轮询与组件卸载竞态导致 setState on unmounted / 幽灵请求] → `usePolling` 统一管理 cancelled 标志与 timer 清理，并配 fake timers 测试锁定
- [前端序列化的 yaml 与后端 schema 存在差异风险] → 保存前强制走 `/check`，由 M9b（M2）兜底拒绝非法文档；`src/types/` 与后端 Pydantic 对齐避免字段漂移
- [编辑器与执行报告页共用节点树渲染，逻辑耦合] → 抽通用无状态节点树组件，业务状态由各 feature hook 持有，单测分别覆盖
- [mock 数据与真实 M9b 行为漂移] → 类型对齐 + 独立 mock server 验收 + 集成测试（前后端实跑）把关

## Migration Plan

- 前端为全新工程，无存量迁移；`npm run dev` 开发，`npm run build` 产物供 M9b 后续静态托管（不在本 change 范围）
- 独立验收路径：以 M9b mock server 提供 API，前端可不依赖真实后端先行交付；后端就绪后切换真实地址做集成验收
- 回滚策略：前端改动互不依赖后端代码，可整体移除 `webops/frontend/` 目录回退