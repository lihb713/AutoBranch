## ADDED Requirements

### Requirement: Define 节点解析

系统 SHALL 解析变量声明节点（`type: Define`）：`vars`（名 → `{type, value}` 的映射，**变量数量不固定**）。`type` SHALL 为合法类型 token；`value` SHALL 为字面量或 `Param.<ASCII名>`（读取当前帧变量做拷贝重命名）。变量名 SHALL 为 ASCII 标识符。`Define` 为叶子节点（无槽位、不展开）；其声明的变量 SHALL 视为"已定义"，供后续 `Param.<名>` 读取通过校验。

#### Scenario: 合法 Define 节点解析
- **WHEN** 文档中出现 `type: Define`，`vars` 含若干 `{type, value}`
- **THEN** 解析为变量声明节点（保留 vars），校验通过

#### Scenario: 变量名非 ASCII
- **WHEN** `vars` 中出现中文/含点号/非 ASCII 的变量名
- **THEN** 清晰度校验失败，报告 `syntax.invalid_name`

#### Scenario: 类型非法
- **WHEN** `vars` 中某变量的 `type` 不是合法类型 token
- **THEN** 清晰度校验失败，报告指明非法类型

#### Scenario: value 引用未定义变量
- **WHEN** 某变量 `value: Param.x`，但 x 未定义
- **THEN** 清晰度校验失败（`scope.get_undeclared`）

### Requirement: 变量声明语法（读 / 写 / 接收）

系统 SHALL 明确三类变量写法：
- **读取**：`Param.<名>` 可出现在 Action / Condition 的描述文本中，以及 `ref` / `FunctionCall` 的 `args` 元素（args 也可为字面量）。
- **写入声明**：`NewParam.<名>[:类型]` SHALL **仅出现在 Action 的 `description`** 中（声明该叶子可写变量集）。
- **接收**：`ref` / `FunctionCall` 的 `returns` 键 SHALL 为**裸 ASCII 名**（隐式创建变量），含 `.`（如 `NewParam.x`）或非 ASCII → 校验错误 `syntax.invalid_return_name`。文档 `inputs`/`outputs` 声明为裸名。

#### Scenario: returns 使用裸名接收
- **WHEN** `ref`/`FunctionCall` 的 `returns` 键为裸 ASCII 名（如 `{loginOk: bool}`）
- **THEN** 校验通过，执行时按该名创建变量

#### Scenario: returns 使用 NewParam 前缀被拒绝
- **WHEN** `returns` 键含 `.`（如 `{NewParam.loginOk: bool}`）或非 ASCII
- **THEN** 清晰度校验失败，报告 `syntax.invalid_return_name`

#### Scenario: NewParam 仅用于 Action 描述
- **WHEN** Action `description` 含 `NewParam.x[:类型]`
- **THEN** 该 x 进入该 Action 的可写变量声明集（产出型工具目标须在其中）