# behavior-tree-parser delta · plugin-capability-expansion

## ADDED Requirements

### Requirement: FunctionCall 命名参数

FunctionCall SHALL 支持位置参数 `args` 与命名参数 `kwargs`；`kwargs` 可按参数名传值并跳过中间可选参数，值支持字面量、`Param.x` 与嵌套 dict/list。校验 SHALL 拒绝未知/重复命名参数与缺失必填参数。

#### Scenario: 跳过中间可选参数

- **WHEN** 调用 `ssh.create_session` 只提供 `host` 与 `kwargs.jump`
- **THEN** 校验通过，其余可选参数使用默认值

#### Scenario: 未知/重复命名参数

- **WHEN** `kwargs` 包含未声明参数或与位置参数重复
- **THEN** 保存校验返回 422
