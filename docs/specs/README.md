# WebOps 模块 Spec 索引

> 依据 `docs/contract.md`（v1.9）第 12 章模块划分，将 WebOps 拆分为 10 个**可独立开发、独立测试、独立交付**的模块单元。
>
> 每个单元对应一份 spec 文档，描述其功能、数据依赖、单元间依赖、接口契约、验收标准与测试策略。

## 模块地图

| 模块 | Spec 文档 | 名称 | 依赖 | 实施阶段 |
|---|---|---|---|---|
| M0 | [M0-llm-client.md](M0-llm-client.md) | LLM 客户端 | 无 | 阶段1 |
| M1 | [M1-browser-driver.md](M1-browser-driver.md) | 浏览器驱动 | 无 | 阶段1 |
| M2 | [M2-behavior-tree-parser.md](M2-behavior-tree-parser.md) | 行为树文档解析器 | 无 | 阶段1 |
| M3 | [M3-schema-namespace.md](M3-schema-namespace.md) | schema 命名空间 | 无 | 阶段1 |
| M4 | [M4-semantic-graph.md](M4-semantic-graph.md) | 语义图生成 | M1 + M0 | 阶段2 |
| M5 | [M5-engine-functions.md](M5-engine-functions.md) | 引擎函数层 | M1 + M4 + M3 | 阶段3 |
| M6 | [M6-leaf-agent.md](M6-leaf-agent.md) | 叶子 agent 执行 | M0 + M5 | 阶段4 |
| M7 | [M7-orchestrator.md](M7-orchestrator.md) | 编排器 + 遍历器 | M2 + M3 + M6 + M8 | 阶段5 |
| M8 | [M8-reporting.md](M8-reporting.md) | 报告机制 | M1 | 阶段2 |
| M9a | [M9a-frontend-ui.md](M9a-frontend-ui.md) | 前端 UI | M9b | 阶段6 |
| M9b | [M9b-management-backend.md](M9b-management-backend.md) | 行为树管理系统后端 | M2 + M7 + M8 | 阶段6 |

## 依赖关系图

```
        ┌──── M0 LLM ────┐
        │                ▼
M2 文档解析   M6 叶子agent  ◄─── M5 引擎函数 ◄─── M4 语义图生成
        │         │                       ▲          ▲
        ▼         ▼                       │          │
M3 schema ◄─── M7 编排器 ────► M8 报告 ◄───┘          │
        ▲         │                       M1 浏览器 ───┘
        └─────────┘
                 │
                 ▼
        ┌──────────────┐
        │  M9b 后端服务  │ ◄── M9a 前端 UI
        │  (内嵌引擎)   │
        └──────────────┘
```

## 实施顺序

- **阶段1（无依赖，可并行）**：M0 / M1 / M2 / M3
- **阶段2（依赖 M1）**：M4 / M8
- **阶段3（依赖 M0+M4+M3）**：M5
- **阶段4（依赖 M0+M5）**：M6
- **阶段5（整合）**：M7
- **阶段6（前端）**：M9a / M9b

## Spec 文档统一模板

每份 spec 文档包含 7 个固定章节：

1. **概述** — 模块定位、在系统中的作用
2. **功能范围** — 功能清单，标注引用契约章节
3. **数据依赖** — 输入/输出数据、数据结构契约
4. **单元间依赖** — 依赖哪些模块、被哪些模块依赖
5. **接口契约** — 对外公开的 API/数据结构定义
6. **验收标准** — 可验证的完成标准
7. **测试策略** — 独立测试方案