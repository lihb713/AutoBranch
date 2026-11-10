## ADDED Requirements

### Requirement: 函数返回参数带类型

插件函数声明多返回值时，`FunctionDef.returns` SHALL 为 `{返回参数名: 类型}` 映射：

- 返回参数名必须是裸 ASCII 标识符 `[A-Za-z_][A-Za-z0-9_]*`；
- 类型必须是 `TYPE_REGISTRY` 合法 token（如 `str/int/float/bool/page_ref/object`）。

注册或校验插件遇到非法返回声明 MUST 拒绝（注册报 `PluginError`，插件校验接口返回可定位错误），且不注册该函数/插件。

#### Scenario: 合法返回声明注册成功
- **WHEN** 插件声明 `returns={"stdout": "str", "stderr": "str", "exit_code": "int"}`
- **THEN** 注册成功，函数可供 FunctionCall 调用

#### Scenario: 名字非法被拒绝
- **WHEN** 插件声明 `returns={"结果": "str"}`
- **THEN** 注册/校验失败并报告非法返回参数名

#### Scenario: 类型非法被拒绝
- **WHEN** 插件声明 `returns={"stdout": "text"}`
- **THEN** 注册/校验失败并报告非法返回类型

#### Scenario: 旧式无类型 returns 被拒绝
- **WHEN** 插件声明 `returns=("stdout", "stderr")`
- **THEN** 校验失败，提示必须使用 `{名称: 类型}` 映射
