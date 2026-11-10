## ADDED Requirements

### Requirement: 参数名与节点 id 规范

文档中所有参数名与节点 id SHALL 为裸 ASCII 标识符 `[A-Za-z_][A-Za-z0-9_]*`：

- `inputs` 的每个键；
- `outputs` 的每个键；
- `nodes` 的每个节点 id；
- `ref` / `FunctionCall` 的 `returns` 接收名。

非法名 MUST 使清晰度校验失败并可定位到声明位置。`tree` 文档名与节点 `name` 显示名不受此限制。

#### Scenario: 合法参数名与节点 id 通过校验
- **WHEN** 文档声明 `inputs: {account: str}`、`outputs: {loginOk: bool}`、节点 id `n1/n2`
- **THEN** 清晰度校验通过

#### Scenario: 非法参数名被判失败
- **WHEN** 文档声明 `inputs: {账号: str}` 或 `outputs: {结果: bool}`
- **THEN** 清晰度校验失败，报告指明非法参数名

#### Scenario: 非法节点 id 被判失败
- **WHEN** 文档声明节点 id `节点1` 或 `n-1`
- **THEN** 清晰度校验失败，报告指明非法节点 id

### Requirement: 文档 outputs 带类型

文档 `outputs` SHALL 为 `{输出名: 类型}` 映射，类型必须是 `TYPE_REGISTRY` 合法 token。解析结果 `decl_outputs` SHALL 保存名称到类型的映射；ref 参数对齐按名称顺序与类型进行校验。

#### Scenario: 带类型 outputs 解析成功
- **WHEN** 文档声明 `outputs: {urlText: str}`
- **THEN** 解析结果包含 `decl_outputs={"urlText": "str"}`

#### Scenario: outputs 类型非法
- **WHEN** 文档声明 `outputs: {urlText: unknown_type}`
- **THEN** 清晰度校验失败并指明非法输出类型

#### Scenario: ref returns 类型与目标 outputs 对齐
- **WHEN** ref 目标声明 `outputs: {urlText: str}`，调用方 `returns: {myUrl: str}`
- **THEN** 校验通过

#### Scenario: ref returns 类型不一致
- **WHEN** 目标输出为 `str`，调用方声明 `{myUrl: int}`
- **THEN** 清晰度校验失败并指明类型不匹配
