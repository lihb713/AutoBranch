# compute-plugin Specification

## Purpose

计算能力插件：提供确定性的数值运算、排序、比较等函数，既可由 LLM 作为工具调用，也可由 FunctionCall 节点直接调用。

## Requirements
### Requirement: 计算函数

系统 SHALL 通过计算插件提供确定性函数（数值运算、排序、比较等）；每个函数 SHALL 声明其参数与多返回值类型；函数只返回值、不写变量。

#### Scenario: 数值运算
- **WHEN** 调用 `multiply(a=2, b=3)`
- **THEN** 返回 `6`

#### Scenario: 排序
- **WHEN** 调用 `sort([3, 1, 2])`
- **THEN** 返回 `[1, 2, 3]`

#### Scenario: 比较
- **WHEN** 调用 `compare(5, 3)`
- **THEN** 返回比较结果（如 `5 > 3` 的布尔 / 关系描述）

### Requirement: 计算函数无副作用

计算函数 SHALL 为纯函数（同输入同输出、无外部副作用），可安全重复调用。

#### Scenario: 重复调用结果一致
- **WHEN** 以相同输入多次调用同一计算函数
- **THEN** 返回一致结果
