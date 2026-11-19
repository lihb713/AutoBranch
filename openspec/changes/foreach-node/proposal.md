## Why

现有行为树只有固定次数/条件循环，缺少“遍历变量列表逐项执行子树”的能力，无法处理 HTTP 返回环境列表后逐个处理的动态场景。

## What Changes

- 新增 `ForEach` 节点：`variables`（临时变量，列表逐项/非列表同值）、`body` 槽位、`on_failure`（continue/abort）。
- 新增运行时 `ForEachNode` 与 `_tick_for_each`：临时子帧执行、列表长度校验、失败策略、结果累积。
- `SchemaSpace` 增加向上读取、`enter_frame(mount=...)`、调用栈恢复；Ref 帧挂 root，ForEach 子帧挂当前树帧。
- `transform` 增加 `append` / `dict_set` 产出型函数（ForEach 累积结果）。
- 前端新增 ForEach 节点编辑（变量行、失败策略、循环体槽位）。

## Impact

- Parser / orchestrator / schema / frontend tree-editor / transform plugin。
- specs、contract、user-guide、README。
