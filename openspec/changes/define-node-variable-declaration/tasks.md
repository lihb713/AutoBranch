# define-node-variable-declaration 任务

## 1. 解析器：Define 节点 + returns 裸名

- [x] 1.1 `parser/models.py` 新增 `DefineNode(vars: tuple[(name, type, value_expr)])`；`onedoc.py` 识别 `type: Define` 构建 IR 与 Define 节点（叶子、不展开）；单测覆盖合法解析、变量数量任意
- [x] 1.2 校验：`vars` 变量名 ASCII、`type` 合法 token、`value` 为 `Param.<ASCII>`（纳入 get_undeclared：x 须已定义）或字面量；Define 声明的变量视为已定义供后续 `Param` 读取；单测覆盖各失败路径
- [x] 1.3 `returns` 键改裸名（不兼容）：`onedoc._append_returns` 校验 `^[A-Za-z_][A-Za-z0-9_]*$`，移除 NewParam 剥离/兼容，含 `.`/非 ASCII → `syntax.invalid_return_name`；更新解析器测试

## 2. 编排器：Define 执行

- [x] 2.1 `traverser._tick_define`：逐变量求值（`Param.x` 读当前帧 / 字面量）→ `coerce(type)` → `space.write(this/<name>)`；求值/coerce 失败 → 节点 FAILURE（原因含变量名）；无截图
- [x] 2.2 单测：创建变量供后续读取、`Param.x` 拷贝重命名、类型 coerce、未定义 Param 失败

## 3. 前端：Define 节点 + returns 裸名

- [x] 3.1 `treeModel.ts` 支持 `Define`（`vars` 解析/序列化，无槽位）；`NodePalette` 增 `Define`
- [x] 3.2 `PropertyPanel` 增"变量"分组（名/类型/值表格，可增删）；`validation.ts` 校验变量名 ASCII、类型 token；组件测试
- [x] 3.3 `returns` 接收名改裸名校验（拒绝 `.`/非 ASCII）；更新前端测试（`treeModel`/`functionCall`/`PropertyPanel`/`validation`）

## 4. 整改、文档与验收

- [x] 4.1 全仓库整改：测试 fixture / e2e（`run-instances`、`plugins`）/ 示例中 `returns: {NewParam.x}` → `{x}`
- [x] 4.2 文档：契约 §4/§5（变量语法、节点表加 `Define`）、M1 parser spec、M5 orchestrator、M9/tree-editor、用户手册、README
- [x] 4.3 全量验证：`pytest`（857 passed）、前端 `lint/typecheck/test`（170 passed）、`ruff` 全绿；非 LLM E2E 全绿（`run-instances`/`plugins`/编辑器渲染）。依赖真实 LLM 的 4 个 Action E2E 因端点拒绝失败（环境问题：`https://opencode.ai/zen/go/v1` 流式/非流式均被拒 `_StreamModeRejected`，与本改动无关），待端点恢复后复跑