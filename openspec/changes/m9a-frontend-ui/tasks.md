## 1. 工程脚手架与基础配置

- [x] 1.1 在 `webops/frontend/` 初始化 Vite + React 18 + TypeScript 工程，配置 `package.json` 脚本（dev/build/lint/typecheck/test/test:e2e）（验证：`npm install` 成功、`npm run build` 产出 dist、`npm run typecheck` 通过）
- [x] 1.2 配置 ESLint 与 tsc（`npm run lint`、`npm run typecheck`）（验证：两命令均无错误退出）
- [x] 1.3 引入 Vitest + React Testing Library + fake timers，配置 jsdom 测试环境与 MSW 或 mock fetch 基础设施（验证：`npm test` 可运行一个最小冒烟测试通过）
- [x] 1.4 建立 `src/` 目录骨架（api/components/features/hooks/types）与设计 token（`src/styles/tokens.css`，SUCCESS/FAILURE/RUNNING 三色）（验证：目录存在、`npm run typecheck` 通过）
- [x] 1.5 引入 react-router-dom 并配置三条路由：列表 `/`、编辑器 `/editor/:id?`、执行报告 `/runs/:runId`（验证：`npm test` 路由渲染冒烟测试通过、dev server 可跳转）

## 2. API 客户端与领域类型

- [x] 2.1 按 `api-conventions.md` 建立 `src/api/request.ts` fetch 封装（JSON 头、非 2xx 抛错、错误信息提取）（验证：单测覆盖成功与失败分支，`npm test` 通过）
- [x] 2.2 实现 `src/api/trees.ts`：listTrees/getTree/createTree/updateTree/deleteTree/checkTree，对应 `/api/trees` CRUD 与 `/api/trees/{id}/check`（验证：API mock 测试断言请求方法与路径正确）
- [x] 2.3 实现 `src/api/runs.ts`：runTree/getRunState/getRunReport/getRunTrace/getReportFile，对应执行与报告接口（验证：API mock 测试断言请求方法与路径正确）
- [x] 2.4 定义 `src/types/` 领域类型（TreeOut、TreeCreate、CheckReport、RunState、NodeInfo、NodeReport 等），字段与后端 Pydantic schema 对齐（snake_case）（验证：`npm run typecheck` 通过，类型被 api 层引用）

## 3. 通用 hooks 与组件

- [x] 3.1 实现 `src/hooks/usePolling.ts`（按 `frontend-style.md` §3.3：intervalMs 默认 1000、shouldStop 停止、卸载清理 timer 与 cancelled 标志）（验证：fake timers 单测覆盖"按时 tick、finished 停止、卸载后不再请求"）
- [x] 3.2 实现通用无状态组件：行为树节点树渲染组件（递归展示复合节点、按状态着色）、按钮/输入框等基础组件（验证：组件测试验证节点树渲染与 SUCCESS/FAILURE/RUNNING 着色类名）

## 4. 行为树编辑器（复合节点视图）

- [x] 4.1 实现编辑器节点模型与 reducer（addNode/updateNode/removeNode/moveNode，节点类型限 Step/Branch/LoopUntil/IfThenElse/Retry/Sequence/ref，叶子可填 action/expect/when/until 等自然语言内容）（验证：reducer 单测覆盖增删改移与非法类型拒绝）
- [x] 4.2 实现节点面板与拖拽：拖拽节点入画布、在节点内添加子节点（验证：组件测试用拖拽事件断言节点入树）
- [x] 4.3 实现 yaml 生成与解析：编辑器树模型 ↔ yaml 文本双向转换（`js-yaml`），复合节点保持书写形态、不展开（验证：单测覆盖合法文档往返一致，`npm test` 通过）
- [x] 4.4 实现 `TreeEditorPage`：加载既有树（`getTree` → 解析进编辑器）与新建树，保存时先 `checkTree` 再提交保存（创建 POST / 修改 PUT）（验证：API mock 测试断言"先 check 后 save"顺序；校验失败时页面展示错误清单且不发保存请求）
- [x] 4.5 校验失败提示交互：展示可读错误清单、引导定位修正节点（验证：组件测试断言校验失败渲染错误清单与阻止保存）

## 5. 行为树管理

- [x] 5.1 实现列表页：加载 `/api/trees` 渲染列表（名称/更新时间），空列表显示空状态，列表项 key 用稳定 id（验证：API mock 测试覆盖列表渲染与空状态）
- [x] 5.2 实现新建入口：跳转编辑器新建并保存后回列表刷新（验证：API mock 测试断言创建后列表刷新）
- [x] 5.3 实现编辑入口与删除：行内删除（DELETE，成功后移除该行）、点击跳转编辑器（验证：API mock 测试覆盖删除成功与 404 错误提示）

## 6. 执行报告页（轮询实时渲染）

- [x] 6.1 实现执行触发：编辑器/列表页点击执行 → `runTree` 取 run_id → 跳转报告页（验证：API mock 测试断言触发并跳转）
- [x] 6.2 用 `usePolling` 轮询 `getRunState`（shouldStop=finished，1 秒间隔）渲染进度条、当前节点高亮、已完成节点 SUCCESS/FAILURE 着色（验证：fake timers 模拟状态序列，断言每次 tick 后 UI 更新、finished 后不再发请求）
- [x] 6.3 渲染节点截图：completed 节点报告中的截图经 `/api/reports/{path}` 加载展示，加载失败显示占位（验证：组件测试覆盖截图加载成功与失败占位）
- [x] 6.4 执行结束后展示完整执行报告（`getRunReport`）与回溯报告（`getRunTrace`）切换视图（验证：API mock 测试断言结束后加载两类报告并渲染）

## 7. 测试与集成验收

- [x] 7.1 组件测试：编辑器拖拽/表单、复合节点视图"仅展示复合节点"（验证：`npm test` 全绿）
- [x] 7.2 API mock 测试：覆盖树列表/创建/查看/修改/删除/校验、执行触发、状态轮询、报告与截图加载、404 等错误路径（验证：`npm test` 全绿）
- [x] 7.3 轮询渲染测试：用 fake timers 模拟完整执行状态序列，断言进度与截图实时更新、执行完成停止轮询（验证：`npm test` 全绿）
- [x] 7.4 配合 M9b mock server 实跑前后端，验证"编辑器生成 → 保存校验 → 执行 → 轮询渲染 → 完整报告"完整链路（验证：dev server + mock server 手工/E2E 走通上述链路；**实际以真实后端完成联调，见 7.5**）
- [x] 7.5 前端与真实 M9b 后端联调集成验收（若后端就绪），对照 `docs/specs/M9a-frontend-ui.md` §6 验收标准逐条核对（验证：`npm run lint`、`npm run typecheck`、`npm test` 全绿且验收标准全部满足；**已完成**：vite dev(5174) → uvicorn(8001) 代理链路，list/create/check/get/run/轮询/report/trace 全通）