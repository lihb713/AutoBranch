# AutoBranch 模块 Spec 索引

> 依据 `docs/contract.md` 模块划分（能力插件化重构后 v2.0），将 AutoBranch 拆分为模块单元：**引擎核心（M0–M6）+ 插件集（M7）+ 管理系统（M8/M9）**。
>
> 每个单元对应一份 spec 文档，描述其功能、数据依赖、单元间依赖、接口契约、验收标准与测试策略。

## 模块地图

| 模块 | Spec 文档 | 名称 | 依赖 |
|---|---|---|---|
| M0 | [M0-llm-client.md](M0-llm-client.md) | LLM 客户端 | 无 |
| M1 | [M1-behavior-tree-parser.md](M1-behavior-tree-parser.md) | 行为树解析器（含 FunctionCall） | 无 |
| M2 | [M2-schema-namespace.md](M2-schema-namespace.md) | 变量空间（泛型 object） | 无 |
| M3 | [M3-plugin-system.md](M3-plugin-system.md) | 插件框架 | 无 |
| M4 | [M4-leaf-agent.md](M4-leaf-agent.md) | 叶子 agent（两级能力选择） | M0 + M2 + M3 |
| M5 | [M5-orchestrator.md](M5-orchestrator.md) | 编排器（FunctionCall/懒装配） | M1 + M2 + M4 + M6 |
| M6 | [M6-reporting.md](M6-reporting.md) | 报告机制（插件驱动） | M3 |
| M7 | [M7-plugin-set.md](M7-plugin-set.md) | 插件集（browser/compute/ssh/file/自定义） | M3 |
| M8 | [M8-management-backend.md](M8-management-backend.md) | 管理后端（文档/运行/插件 API） | M1 + M5 + M6 + M3 + M7 |
| M9 | [M9-frontend-ui.md](M9-frontend-ui.md) | 前端 UI（行为树编辑器 + 插件管理） | M8 |

> 原 M1 浏览器驱动、M4 语义图、M5 引擎函数层已并入 **M7 插件集**（浏览器插件内部实现），不再作为独立模块。

## 依赖关系图

```
引擎核心                 插件框架               插件集
M0 LLM ─┐               M3 插件框架 ──注册──►  M7 插件集
M1 解析 ─┼─► M4 叶子agent         ▲            (browser/compute/ssh/file/自定义)
M2 变量 ─┘      │                 │ 分发
               ▼                 │
         M5 编排器 ──► M6 报告 ◄──┘
               │
               ▼
         M8 管理后端 ◄── M9 前端 UI
         (内嵌引擎 + 插件 API)
```

## 实施顺序

- **引擎核心基础（无依赖，可并行）**：M0 / M1 / M2 / M3
- **插件集**：M7（依赖 M3）
- **叶子/编排/报告（依赖 M0–M3）**：M4 / M5 / M6
- **管理系统**：M8 / M9（依赖引擎 + 插件）

## Spec 文档统一模板

每份 spec 文档包含固定章节：概述 / 功能范围 / 数据依赖 / 单元间依赖 / 接口契约 / 验收标准 / 测试策略。