## Context

见 `proposal.md - Why`。核心事实：

- 当前 `FunctionDef.returns` 与文档 `outputs` 都只有名字，没有类型；节点 `returns` 的 `{接收名: 类型}` 要求用户在 UI 选择类型。
- 当前编辑器是前端本地文档模型，保存时才上传；新增节点不会访问后端。
- 运行期 `FunctionCall` / `ref` 按 `node.returns` 顺序写变量；缺失项静默丢弃。
- 跨文档 ref 经 `DbResolver` 按文档名加载，目前不检查目标文档状态。

## Goals / Non-Goals

**Goals:**
- 接收名称与类型全部自动生成；用户只可改名称。
- 参数名与节点 id 全 ASCII，历史数据迁移。
- 后端作为唯一文档权威；草稿/正式单文档状态机。
- 删除/槽位/节点/默认名/类型/校验逻辑全部后端单一实现。

**Non-Goals:**
- 不做撤销/重做。
- 不做前端离线编辑或本地草稿副本。
- 不做“跳过某个返回值”；所有返回值都必须接收。
- 不迁移历史执行快照 `runs.content_snapshot`。
- 不改 `tree` 文档名和节点显示名（保持中文）。

## Decisions

### D1. 单文档状态机

- `Tree.status ∈ {draft, published}`，默认历史记录为 `published`。
- 新建即 `draft` + 临时名 `未命名-<时间戳>`；首次保存校验、改名、转 `published`。
- 对 `published` 的任何修改 → 同记录转 `draft`，不复制。
- 只有 `published` 可执行；ref 目标必须 `published`。
- 删除即删除记录。

### D2. 命令式编辑 API

- `POST /api/trees/drafts`：创建草稿（临时名 + 空文档）。
- `POST /api/trees/{id}/commands`：一次提交一个或多个命令，后端应用到文档、归一化、返回完整 `TreeDetailOut`。
- 命令：
  - `add_node {type}`（Step 自动附带 Action）
  - `delete_node {node_id, subtree}`
  - `update_node {node_id, patch}`（结构字段/fields/function/target/args/returns/vars 等）
  - `update_doc {patch}`（`tree`/`inputs`/`outputs`/`config`）
- `POST /api/trees/{id}/save`：校验 + 改名 + 发布。
- 命令执行后状态置 `draft`；草稿允许校验失败。
- 前端只保存 UI 状态（选中、Tab、拖拽）；文档内容全部来自后端响应。

### D3. 名称与类型来源

- `FunctionDef.returns: dict[str, str]`（名称→类型）。
- 文档 `outputs: dict[str, str]`（名称→类型）。
- `FunctionCall` 默认接收类型 = `spec.returns[name]`。
- `ref` 默认接收类型 = 目标文档 `outputs[name]`。
- 节点 `returns` 仍存 `{接收名: 类型}`，类型只读、自动刷新。
- 泛型/多态返回使用合法类型 token `object`（如页面对象、列表、int|float）。

### D4. 默认名与冲突

- 默认名 `<node_id>_<return_name>`。
- 按来源返回声明顺序对位补名；已有名称保留；数量多于声明时截断。
- 自动名与文档变量（`inputs`、`outputs`、`Define`、`Action NewParam`、其他 `returns`）冲突时追加 `_1`、`_2`。
- 手工名称不重命名；冲突由保存校验处理（重复变量/未定义引用）。
- 名称/类型变更不自动改写 `Param.<旧名>` 引用。

### D5. ASCII 命名与迁移

- 节点 id、`inputs` 键、`outputs` 键、`FunctionDef.returns` 名称、`returns` 接收名必须是 `[A-Za-z_][A-Za-z0-9_]*`。
- 历史 `trees.content` 迁移：
  - 非 ASCII `inputs` → `input1/input2...`，改写本树 `Param.<旧名>`；
  - 非 ASCII `outputs` → `output1/output2...`，改写本树 `NewParam.<旧名>`；
  - 非 ASCII 节点 id → 文档顺序 `n1/n2...`，改写 `root`/槽位引用；
  - 非 ASCII 接收名 → 用新节点 id 生成默认名，改写本树 `Param.<旧名>`；
  - `outputs` 类型按 `NewParam`/`Define`/来源节点推断，推断不出用 `object`；
  - 现有树迁移后置 `published`；清空 `experiences`。
- `runs.content_snapshot` 不迁移。

### D6. 后端单一归一化实现

- 新增后端归一化服务，完成默认名/类型、冲突、类型刷新、ASCII 校验。
- 被草稿命令、保存、迁移脚本、运行前兜底复用。
- 前端不再实现默认名/类型/冲突/结构修改；只展示后端返回文档。

## Risks / Trade-offs

- [兼容性] 函数 `returns` 与文档 `outputs` 格式 Breaking，需要迁移内置插件、测试、文档与历史文档。
- [草稿语义] 正式树被修改立即变草稿且不可执行；引用它的树也不可执行，直到重新保存。这是预期行为。
- [迁移] 改名可能影响变量引用；迁移脚本负责改写，迁移后清空经验避免 hash 失配。
- [性能] 每次命令返回完整文档；文档规模小，可接受。文本编辑需 debounce/onBlur。
