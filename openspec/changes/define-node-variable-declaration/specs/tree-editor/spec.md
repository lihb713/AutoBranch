## ADDED Requirements

### Requirement: Define 节点编辑

编辑器 SHALL 支持新增与编辑 `Define` 节点：节点面板提供 `Define` 项；属性面板以"变量名 / 类型 / 值"行表格编辑 `vars`（可增删行，类型为类型 token 下拉，值为文本）。`Define` 无槽位子节点。保存/校验时 SHALL 校验变量名 ASCII、类型合法。

#### Scenario: 添加 Define 节点
- **WHEN** 用户从节点面板添加 `Define` 节点
- **THEN** 画布新增该节点（无槽位），属性面板展示变量行表格

#### Scenario: 编辑变量行
- **WHEN** 用户在属性面板增删/修改某变量行（名/类型/值）
- **THEN** 节点 `vars` 同步更新并可保存为 `type: Define`

### Requirement: returns 接收名裸名编辑

编辑器中 `ref` / `FunctionCall` 的 `returns` 接收名输入 SHALL 接受**裸 ASCII 名**；含 `.`（如 `NewParam.x`）或非 ASCII → 即时校验报错。

#### Scenario: 裸名接收
- **WHEN** 用户在某 `returns` 行输入 `loginOk`
- **THEN** 校验通过，保存为 `returns: {loginOk: <类型>}`

#### Scenario: 点号/非 ASCII 被拒绝
- **WHEN** 用户输入 `NewParam.loginOk` 或中文名
- **THEN** 即时校验报错（`syntax.invalid_return_name`）