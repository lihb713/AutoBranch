# transform-plugin Specification

## Purpose

数据提取与变换插件：从嵌套列表/字典按路径取值，处理字符串、JSON、正则与通用比较，作为确定性 FunctionCall/LLM 工具使用。

## Requirements

### Requirement: 数据提取

系统 SHALL 提供 `transform.get_path(data, path, required?, default?)`，支持点路径（如 `0.a.b.1`）与方括号写法（如 `a[0].b[-1]`）；另提供 `get_index` / `get_key`。路径不存在时默认失败，`required=false` 时返回 `default`。

#### Scenario: 嵌套路径
- **WHEN** 调用 `get_path({"a":[{"b":[10,20]}]}, "a.0.b.1")`
- **THEN** 返回 `20`

#### Scenario: 路径不存在
- **WHEN** 调用 `get_path(data, "a.x")` 且 required 默认 true
- **THEN** 返回失败结果

### Requirement: 字符串与容器变换

系统 SHALL 提供 `split` / `join` / `contains` / `index_of` / `replace` / `strip` / `length` / `slice` / `keys` / `values`，覆盖字符串切分拼接、搜索替换、列表切片与字典键值提取。

### Requirement: 类型/JSON/正则/比较

系统 SHALL 提供 `to_string` / `to_int` / `to_number` / `to_bool`、`json_parse` / `json_dumps`、`regex_match` / `regex_extract` / `regex_findall`，以及 `compare(a,b,op,ignore_case)`（eq/ne/gt/ge/lt/le/contains/startswith/endswith）。

#### Scenario: 正则提取
- **WHEN** 调用 `regex_extract("id=42", r"id=(\d+)", group=1)`
- **THEN** 返回 `"42"`
