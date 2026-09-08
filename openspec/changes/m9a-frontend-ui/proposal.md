## Why

WebOps 目前只有引擎与后端 API，缺少人机交互界面，用户无法可视化地书写含复合节点的行为树、管理文档或观察执行过程。依据契约 §12.4/§12.5，需要提供纯前端 UI（M9a）：拖拽式行为树编辑器、行为树管理 CRUD、1 秒轮询的执行报告页，让用户以"始终含复合节点"的视图完成从书写到验收的完整闭环。

## What Changes

- 新增**行为树编辑器**：拖拽节点 + 填写自然语言信息 → 生成含复合节点（Step/Branch/LoopUntil/IfThenElse/Retry/Sequence/ref）的行为树 yaml 文档（契约 §12.5/§4.3）
- 新增**复合节点视图**：用户始终看到含复合节点的行为树，引擎基础节点对用户不可见，前端不展开复合节点
- 新增**行为树管理页**：列表/查看/修改/删除（CRUD），消费 M9b 管理 API
- 新增**保存时清晰度校验提示**：保存前调用 `/api/trees/{id}/check`，校验失败以友好错误清单提示用户修正
- 新增**执行报告页**：点击执行触发 `/api/trees/{id}/run` 获取 run_id，每 1 秒轮询 `/api/runs/{run_id}/state`，实时渲染节点成功/失败状态与截图，执行完毕后展示完整执行报告与回溯报告（契约 §12.4）
- 建立前端工程基础：React 18 + TypeScript + Vite 工程、统一 API 访问层、通用轮询 hook、与后端 schema 对齐的类型定义
- 非目标（第一版）：不做 WebSocket 实时推送，采用 1 秒轮询（契约 §12.4）

## Capabilities

### New Capabilities
- `frontend-ui`: 纯前端用户界面能力——拖拽式行为树编辑器（产出含复合节点的行为树文档）、行为树管理 CRUD、保存时清晰度校验提示、1 秒轮询的执行报告页（实时渲染节点进度与截图、展示完整执行与回溯报告），全部依赖 M9b 后端 API

### Modified Capabilities
<!-- 无既有 capability 的需求发生变更 -->

## Impact

- **新增代码**：`webops/frontend/` 下的 Vite 前端工程（`src/api/` API 客户端、`src/types/` 领域类型、`src/hooks/` 轮询 hook、`src/components/` 通用组件、`src/features/tree-editor|runs|reports/` 业务模块），对应 `docs/specs/M9a-frontend-ui.md` 第 5 章接口契约
- **被依赖方**：无（M9a 是最上层，仅消费 M9b）
- **消费 API**：`/api/trees` CRUD、`/api/trees/{id}/check`、`/api/trees/{id}/run`、`/api/runs/{run_id}/state|report|trace`、`/api/reports/{path}`
- **外部依赖**：新增 npm 依赖（React 18、TypeScript、Vite、测试库）；遵循 `.opencode/rules/frontend-style.md` 与 `.opencode/rules/api-conventions.md`
- **测试影响**：组件测试、API mock 测试、轮询渲染测试；可配合 M9b mock server 独立验收