# define-node-variable-declaration 设计

## Context

现状：`ref`/`FunctionCall` 的 `returns` 键被强制 `NewParam.` 前缀（onedoc.py `_strip_return_name` + 前端 `checkReturnKeys`）；`NewParam.` 在描述里作为写声明。无声明变量的节点。`Define` 需作为新叶子节点贯穿解析器（M2）→ 编排器（M7）→ 前端（M9）。

## Goals / Non-Goals

**Goals:**
- `returns` 键裸名（隐式创建），不兼容 `.`/`NewParam.` 前缀。
- `NewParam.` 仅 Action 描述。
- 新增 `Define` 叶子节点：`vars` 变长 `{name: {type, value}}`，`value` 为 `Param.x` 或字面量，coerce 后写当前帧。

**Non-Goals:**
- 不引入新的类型 token。
- 不做 Define 的结构化输出（它只写当前帧变量；要对外用 outputs/ref）。

## Decisions

### D1. `DefineNode` 数据模型
- `parser/models.py` 新增 `DefineNode(Node)`：`vars: tuple[(name, type, value_expr)]`（value_expr 为字符串：`Param.x` 或字面量文本）。
- `onedoc.py` 构建 IRNode（kind=`Define`）；`document.py`/`expand.py` 将 `Define` 视为叶子（非复合，不展开），产出 `DefineNode`。

### D2. Define 解析与校验
- `vars` 为映射；键 = 变量名（ASCII 校验）；值 = `{type, value}`。
- `type` 必须是 `TYPE_REGISTRY` token（否则校验错误）。
- `value` 若匹配 `Param.<ASCII>` → 记为读取（纳入 `scope.get_undeclared` 校验：x 必须是 inputs/NewParam/returns/其它 Define 已定义变量）；否则按字面量。
- Define 声明的变量名进入"块内已定义变量"集合，供后续 `Param.x` 读取通过。

### D3. Define 执行（编排器）
- `traverser._tick_define`：对该节点 `vars` 逐项：
  - 求值 `value`：`Param.<名>` → 读当前帧（复用 `_eval_arg` 语义）；否则 `_parse_literal`。
  - `coerce(type, value)`；写入 `space.write(frame, f"this/{name}", value, type)`。
  - 求值/coerce 异常 → 节点 FAILURE（`_note_failure` 含变量名与错误）。
- 无 LLM、无截图（`used_browser=False` 天然成立）。

### D4. returns 键裸名（不兼容）
- `onedoc._append_returns`：键必须匹配 `^[A-Za-z_][A-Za-z0-9_]*$`；否则 `syntax.invalid_return_name`。**移除** `NewParam.` 前缀的剥离与"legacy 兼容"。
- 前端 `validation.checkReturnKeys` 同步：裸 ASCII；`. `/非 ASCII 报错；`stripReturnName` 简化为原样（不再剥 NewParam）。
- 迁移：所有 `returns: {NewParam.x: ...}` 改为 `{x: ...}`（测试/ e2e / 文档）。

### D5. 前端 Define 节点
- `treeModel.ts`：`TreeNode` 增 `vars?: Record<string, { type: string; value: string }>`；`Define` 加入节点类型；`parseDoc`/`serializeDoc` 读写 `vars`。
- `NodePalette` 增 `Define`；`PropertyPanel` 增"变量"分组（名/类型/值表格，可增删）；`validation.ts` 校验变量名 ASCII、类型 token。
- `Define` 无槽位（`slotFields` 返回空）。

### D6. 兼容与迁移
- `returns` 裸名是 BREAKING：现有库中旧文档（含 `NewParam.` 前缀）保存/执行会被校验拒绝；提供说明（用户手册），不做自动改写（按用户"完全整改"要求）。

## Risks / Trade-offs

- **BREAKING 整改面大**：所有 `returns: {NewParam.x}` 需改裸名；好在集中在测试/e2e/文档。
- **`Param.x` vs 字面量歧义**：与 `ref`/`FunctionCall` 的 `args` 一致（`Param.x` 视为读取，其余字面量）；`Define` 沿用同一规则，用户可理解。
- **Define 只在当前帧写变量**：跨文档输出仍需 `outputs`+`returns`（符合当前作用域模型）。

## Migration Plan

无 DB 迁移。整改文档与现有测试/e2e 中的 `returns` 写法；冒烟/全量测试通过。

## Open Questions

- 无阻塞项。