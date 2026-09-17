## Why

当前 Action / Condition 实质只支持**网页操作**（LLM agent + 浏览器工具集），引擎核心与"浏览器/页面"强耦合。用户需要更通用的自动化能力：数值运算、判断并写变量、排序、文件对比、远程虚拟机执行命令等。本变更把 WebOps 从"网页自动化工具"推进为**通用的、可扩展的 LLM 行为树自动化工具**，网页自动化退化为**其中一项能力**。

## What Changes

**统一函数注册表 + FunctionCall 节点**
- 引入统一函数注册表：同一批函数既可作为 LLM 工具（描述驱动），也可被 FunctionCall 节点直接调用（确定性、不经 LLM）。
- 新增 **FunctionCall 节点**（≈ ref 的"函数版"）：`function` + `args` + `returns`（多返回值），像 ref 一样有入参/出参接口。

**插件模型（引擎核心 / 插件框架 / 插件 三层）**
- **插件类**：`name` / `description` / `function_defs()`（结构化 `FunctionDef`）/ `init(runtime)` / `call()`。
- **插件框架**：注册表（known/loaded/functions）、懒装配、框架工具 `use_capability`、分发、统一 reporting 接口。
- **两级能力选择**：能力概览 + `use_capability(name)` → 引擎加载插件（`init`）→ 该能力函数追加进工具集 → LLM 细选函数；复用 `tool_calls`，无需新输出协议。
- **懒装配**：发生在调用分发时；浏览器等重资源 run 内首次用到才启动、run 结束释放。
- **不做安全机制 / 不做重试声明**（插件由内部开发者提供）。

**浏览器降格为插件（BREAKING）**
- 浏览器驱动 + 语义图**并入浏览器插件**（不再是独立模块）。
- 变量读写归引擎核心：**插件只返回值，引擎落笔写变量**（`output_param` 标明产出型工具）。
- 截图在 `semantic_graph`（"看页面"）时由浏览器插件产出，不再由编排器无条件截。
- 类型系统引入**泛型对象类型**：`page_ref` 纳入泛型（浏览器插件的对象），引擎核心不再有页面概念。

**报告插件驱动**
- 报告 = 引擎基础字段（node_type/desc/result/timestamp/action_call/llm_trace）+ 插件附加信息（`FunctionResult.report`，引擎落笔，统一结构化接口）。

**插件来源与组织**
- 预置插件：文件系统（`plugins/` 包），启动扫描 + import；可依赖 `common` 共享库 + 三方库。
- 用户自定义插件：源码存 DB，`compile + exec` 加载；**仅标准库**，不 import 其他插件/`common`/三方库。
- `common` 为共享库（非插件，不对 LLM 暴露）。

**插件管理（前端 + 后端）**
- 后端插件 API（CRUD + 校验 + 关联查询）+ `plugin` 表（`kind`: builtin|custom）。
- 前端插件管理页（列表 + CodeMirror 6 编辑器 + 保存校验 + 删除关联提示）。

**模块重编排（BREAKING）**
- 引擎核心：M0 LLM / M1 解析 / M2 变量空间 / M3 插件框架 / M4 叶子 agent / M5 编排器 / M6 报告。
- M7 插件集（浏览器/计算/SSH/文件 + 自定义）；M8 管理后端；M9 前端。
- 移除旧 M5 引擎函数层、独立浏览器驱动、独立语义图模块。

## Capabilities

### New Capabilities
- `plugin-system`: 插件框架——插件类 / FunctionDef / 注册表 / 懒装配 / 两级能力选择（use_capability）/ 分发 / 统一 reporting 接口。
- `browser-plugin`: 浏览器插件——浏览器驱动 + 语义图 + 浏览器函数（open/click/extract/semantic_graph…），自包含（ref_map/截图/页面对象）。
- `compute-plugin`: 计算插件——数值运算 / 排序 / 比较等确定性函数。
- `ssh-plugin`: SSH 插件——创建/关闭会话、远程执行命令等。
- `file-plugin`: 文件插件——读写 / 对比 / 路径操作等。
- `plugin-management`: 插件管理——后端插件 API（CRUD/校验/关联查询）+ `plugin` 表 + 前端管理页。

### Modified Capabilities
- `behavior-tree-parser`: 新增 FunctionCall 节点；类型系统引入泛型对象类型。
- `schema-namespace`: 泛型对象类型（`page_ref` 泛型化）；移除页面变量特殊概念。
- `leaf-agent`: 两级能力选择 + 懒装配触发；去强制语义图预取；变量写入落笔；报告信息随返回值产出。
- `orchestrator`: 变量写入落笔；报告改由插件驱动；懒装配的分发与生命周期挂接。
- `reporting`: 报告字段改为「引擎基础 + 插件附加」，提供统一结构化写入接口。

### Removed Capabilities
- `engine-functions`: 由 `plugin-system` 取代（M5 引擎函数层演化为插件框架）。
- `browser-driver`: 并入 `browser-plugin`。
- `semantic-graph`: 并入 `browser-plugin`。

## Impact

- **引擎** `webops/`：`engine/`（M5 → 插件框架）、`browser/` + `semantic_graph/`（→ browser-plugin）、`parser/`（+FunctionCall）、`schema/`（泛型类型）、`leaf_agent/`（两级选择/落笔）、`orchestrator/`（落笔/报告/懒装配）、`reporting/`（插件驱动接口）。
- **插件**：新增 `plugins/` 目录（browser/compute/ssh/file 预置包 + common 共享库）。
- **后端** `webops/server/`：插件 API + `plugin` 表 + 插件加载/重载。
- **前端** `webops/frontend/`：插件管理页（CodeMirror 6）+ FunctionCall 节点编辑。
- **文档**：`docs/contract.md`、`docs/specs/` 按新模块重编排。
