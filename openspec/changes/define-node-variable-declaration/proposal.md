# define-node-variable-declaration 提案

## Why

当前变量声明语义混乱：`NewParam.` 被要求出现在 `ref`/`FunctionCall` 的 `returns` 键里，但"接收返回值 = 创建变量"本身语义清晰、无歧义，不需要显式前缀；只有 **Action 描述（非结构化文本）** 才需要 `NewParam.` 这类标记来区分"变量声明"与普通文字。同时缺少一个专门的"声明/定义变量"节点：用户想创建带初始值的变量（常量、别名拷贝）时，只能借 Action 描述里的 `NewParam.`，语义别扭。本变更收敛变量声明语法并新增 `Define` 节点。

## What Changes

- **`returns` 键改为裸名（不兼容旧写法）**：`ref` / `FunctionCall` 的 `returns` 键 SHALL 为**裸 ASCII 名**（`[A-Za-z_][A-Za-z0-9_]*`），接收即隐式创建变量；含 `.`（如 `NewParam.x`）或非 ASCII → 校验错误 `syntax.invalid_return_name`。**不兼容**：现有使用 `NewParam.` 前缀的树/测试/文档/e2e 全部整改。
- **`NewParam.` 仅用于 Action 描述**：显式写声明（`NewParam.x[:类型]`）只出现在 Action 的 `description`；Condition 文本与 `ref`/`FunctionCall` 的 `args` 只用 `Param.x`（Condition 不声明写变量）；文档 `inputs`/`outputs` 用裸名。
- **新增 `Define` 节点**（叶子、确定性、无 LLM）：`vars`（数量不固定）逐个变量 `{type, value}`——`type` 为类型 token，`value` 为 `Param.x`（拷贝当前帧变量并重命名）或字面量，coerce 到 `type` 后写入当前帧。执行后这些变量即可被后续 `Param.x` 读取（视为已定义）。无槽位、无截图。
- **前端支持**：节点面板新增 `Define`，属性面板提供"名 / 类型 / 值"可增删表格；`ref`/`FunctionCall` 的 `returns` 接收名输入改为裸名校验（拒绝 `.`/非 ASCII）。

**BREAKING**：`returns` 不再接受 `NewParam.` 前缀（含 `.` 即校验失败）；旧文档需改写为裸名。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `behavior-tree-parser`: 新增 `Define` 节点解析与校验；明确变量声明语法（`returns` 裸名、`NewParam.` 仅 Action 描述、`Param.x` 读取位置）。
- `orchestrator`: 新增 `Define` 节点执行（按 `{type,value}` 在当前帧创建变量、支持 `Param.x` 拷贝与类型 coerce）。
- `tree-editor`: 编辑器新增 `Define` 节点（面板/属性/校验）与 `returns` 裸名编辑校验。

## Impact

- **解析层**：`autobranch/parser/onedoc.py`（`Define` 节点解析；`returns` 键改为裸名校验）、`document.py` / `models.py`（`DefineNode` 与变量声明 IR）、`expand.py` / `checks.py`（变量契约：Define 声明的变量视为已定义；returns 裸名）。
- **编排层**：`autobranch/orchestrator/traverser.py`（`Define` 节点 tick：求值/coerce/写帧）、`models.py`（`DefineNode` 消费）。
- **前端**：`tree-editor/treeModel.ts`（`Define` 节点与 `vars` 解析/序列化、`returns` 裸名）、`NodePalette`/`PropertyPanel`/`validation.ts`。
- **整改**：所有使用 `returns: {NewParam.x: ...}` 的树/测试/e2e/fixture 改为裸名；文档（契约 §4/§5、M1/M5/M9 spec、用户手册、README）。
- **测试**：解析（Define 解析/校验、returns 裸名与拒绝点号）、编排（Define 执行/拷贝/coerce/失败）、前端（节点/面板/校验）、e2e。

**依赖**：无。