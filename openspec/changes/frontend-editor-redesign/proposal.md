## Why

现有前端编辑器（嵌套卡片列表 + 单块编辑）与用户期望相差甚远：不是真实节点画布、ref 参数（args/returns）在编辑器打开保存时会静默丢失（数据破坏缺陷）、块声明不可见/不可编辑、附属块概念冗余。此外，行为树文档格式（`block`/多块）已不满足"一文档一树 + 文档自包含"的演进方向，而跨文档引用（`ref: 文档名`）在 server 生产环境从未真正可用（缺 DB-backed 文档库）。

## What Changes

**前端编辑器重写（BREAKING：交互与数据模型完全更换）**
- 真实画布节点（固定尺寸卡片、类型用图标/颜色区分、用户自定义 name），根在上向下生长、兄弟水平排布；主树区 + 游离区自动布局。
- 节点对象池 + 槽位引用：父子关系通过容器节点的 `slots`（下拉选择）建立，只能选"游离根"；删除语义矩阵（删槽位=解引用回游离区、删单节点=子树各自成游离树、删子树=连带删后代）。
- ref 节点：下拉选目标文档 → 自动加载其 inputs/outputs → 填 args/returns；可展开（只读预览）/收缩。
- 两层校验（拓扑：单根/逐树无环；节点配置：必填字段），编辑时即时标记，错误越早越好。
- 移除块列表（BlockListPanel）；根节点为真实节点类型。

**DSL 重定义（BREAKING：行为树文档格式完全更换）**
- 一文档一树：`tree: <名>` + 文档级 `inputs`/`outputs` + 全局配置 + `nodes:`（节点对象池平铺）+ `root: <id>`。
- 节点模型含 `id`（自动生成、导入保留）与 `name`（用户自定义）。
- **统一槽位模型**：节点间一切动作关联经**语义命名字段**引用子树根 id（`Root.body` / `Sequence.actions` / `Step.action` / `IfThenElse.then+else` / `Branch.action+branches[].action` / `Retry.body` / `LoopUntil.action`）；新增 **Action 叶子**（`description`）；**Condition 为概念性节点**内嵌为字段（`Step.expect`/`IfThenElse.if`/`Branch.when`/`LoopUntil.until`）。
- ref 参数对称：`args`（列表，传参）与 `returns`（字典，接收）。

**跨文档引用文档库（BREAKING：`this/块` 同文档引用不再存在）**
- DB-backed resolver：按文档名从 DB 加载文档喂给 `RefResolver`（替换 server 空 `MappingResolver`）。
- 按文档名查 API（`GET /api/trees/by-name/{name}`）。
- `_tick_ref` 按文档名加载被引文档树，从其 Root 执行。
- 文档允许含游离树（草稿保存）；校验允许单根 + 逐树无环。

## Capabilities

### New Capabilities
- `frontend-editor`: 行为树可视化编辑器——真实画布、节点对象池 + 槽位引用、主树/游离区布局、ref 参数编辑与展开/收缩、两层校验、文档导入导出。（取代既有 m9a 前端编辑器交互，原 frontend-ui delta 并入本 capability。）

### Modified Capabilities
- `behavior-tree-parser`: DSL 从"多块（block）+ 树形嵌套"改为"一文档一树（tree/nodes/root）+ 节点平铺 + 槽位引用"；移除 `this/块名` 同文档引用；文档级接口声明。
- `orchestrator`: ref 语义从"按块名查找"改为"按文档名加载被引文档 Root 执行"；blocks_tree 语义变化；跨文档执行经文档库。

## Impact

- **前端** `autobranch/frontend/src/features/tree-editor/`：重写 CanvasTree（画布布局 + SVG 连线 + 主树/游离区）；model.ts 重构（节点对象池/槽位引用/id+name）；ref args/returns 编辑（修复数据丢失）；BlockListPanel 移除；属性面板（ref 参数、节点字段）。
- **M2 parser** `autobranch/parser/`：新 DSL 解析（tree/nodes/root）；删多块解析。
- **M7 执行器** `autobranch/orchestrator/`：ref 按文档名加载；blocks_tree → 文档名→树。
- **后端 API** `autobranch/server/`：按名查文档 API；DB-backed resolver；文档导入。
- **文档** `docs/contract.md`（§4.1 文档格式、§5.7 块引用/帧模型）、各模块 spec 需同步。