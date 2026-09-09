# WebOps — 自然语言驱动的 Web 自动化工具

## 项目概述

用户书写**行为树文档**（yaml/dict，结构确定），WebOps 用 LLM 理解页面、在叶子节点（Action/Condition）内执行有界代理动作，输出操作日志与页面截图。核心设计：**流程流转确定，LLM 只在单节点内行使有限执行权**。详细契约见 `docs/contract.md`。

- **引擎层**（Python）：M0 LLM 客户端 / M1 浏览器驱动（Playwright）/ M2 行为树解析器 / M3 schema 命名空间 / M4 语义图 / M5 引擎函数 / M6 叶子 agent / M7 编排器 / M8 报告
- **管理系统**：M9b 后端（FastAPI）+ M9a 前端（React + TypeScript + Vite）

模块 spec 见 `docs/specs/`（M0~M9b 各一份）。

## 开发与协作约束

1. **独立的 conda 环境**：本机已安装 conda，项目开发与测试验证必须创建**独立的 conda 环境**（如 `conda create -n webops python=3.x`），禁止使用本机已有环境。依赖安装、测试、运行一律在该环境内执行。
2. **docs 为准，实时维护**：`docs/` 是项目的整体说明书。修改或生成代码前，先阅读 `docs/contract.md` 与对应模块 spec（`docs/specs/`）了解设计；**每次修改或生成代码后，同步更新 `docs/contract.md` 与相关模块的 spec 文档**，保持说明书与代码一致。
3. **测试与实机验收**：每次修改代码都必须设计对应的测试用例，特别是**集成化测试**。项目含前后端时，需**实际运行前端与后端进行功能测试**，不能仅凭单元测试通过验收。
   - **端到端测试（E2E）必做**：任何涉及管理系统的改动，必须包含**通过模拟前端操作**的端到端测试（Playwright 驱动真实浏览器操作 UI：点击/跳转/断言页面），**不得只用后端 API 调用或单元测试代替**。E2E 覆盖"前端执行行为树 → 轮询渲染 → 报告展示"核心用户链路（`webops/frontend/e2e/`，`npm run test:e2e`）。
   - **E2E 重点**：前端**执行**行为树并在前端**查看执行结果**是否符合预期（执行/轮询/报告渲染）。编辑器拖拽构建等复杂 UI 操作不是测试重点，可由组件测试覆盖，E2E 中用 API 预置数据，**不必模拟拖拽**。
4. **全程使用中文**：对话交流与文档编写一律使用中文。
5. **端口约定**：本机 **8000 与 5173 端口被 NexusOps 项目占用，禁止使用**。WebOps 使用独立端口组：**M9b 后端本地开发用 8001**（`uvicorn ... --port 8001`），**前端 Vite 开发用 5174**（`webops/frontend/vite.config.ts` 已固定 `strictPort: true`）。一键启动见项目根 `dev-restart.ps1`。

## 核心构建命令

```bash
# conda 环境（每次操作前先激活）
conda create -n webops python=3.11 -y
conda activate webops

# 后端引擎（Python，在 webops 环境内）
pip install -e .
pytest                                        # 引擎单元测试
pytest -m integration                         # 集成测试（真实浏览器）

# 管理系统后端（FastAPI，在 webops 环境内；注意禁用 8000，用 8001）
uvicorn webops.server.main:app --reload --port 8001   # 本地开发

# 管理系统前端（React + TS + Vite）
npm install
npm run dev                                   # 本地开发
npm run build                                 # 生产构建
npm run lint                                  # ESLint
npm run typecheck                             # tsc --noEmit
npm test                                      # Vitest 单元测试
npm run test:e2e                              # Playwright E2E 测试
```

## 规范索引

| 领域 | 规范文件 |
|---|---|
| API 接口设计 | `.opencode/rules/api-conventions.md` |
| 前端组件与状态管理 | `.opencode/rules/frontend-style.md` |
| 数据库设计与 SQL 约束 | `.opencode/rules/database-rules.md` |
| 单元测试与 E2E 测试 | `.opencode/rules/testing-guidelines.md` |

> 编写对应领域代码前，先阅读对应规范文件。

## 前端设计法则

- **不提供不合理的选择**：任何下拉/选择器只展示用户当前可选的选项；不可选的选项不渲染、不出现在列表中。例如容器槽位选择子节点时，只展示"游离树的根节点"（未被任何槽位引用的节点），已挂载节点不展示——保证纯树结构，避免共享子树成图。
- **操作与结构语义一致**：删除槽位 = 解引用（子节点回游离区）；删除单节点 = 其各槽位子节点各自成为游离树；删除子树 = 连带删除后代。编辑/删除动作的结果要可预测、不产生歧义。