## MODIFIED Requirements

### Requirement: 类型契约

创建变量 SHALL 声明类型（`TYPE_REGISTRY` token 之一：`str`、`int`、`float`、`bool`、`object`）；类型即真实存储类型，`set` 标注驱动的 `coerce` SHALL 把网页提取值转成声明类型后存储；写入与提取时系统 SHALL 强校验类型（`isinstance`），类型不匹配或转换失败导致断言失败并终止流程。`object` 为**泛型对象类型**——不校验（任意对象值），呈现用 `str(value)`（由对象类型的 `__str__` 定义），用于承载插件对象（页面对象 / 会话 / 文件句柄…）；引擎 SHALL 记录其实际类型（来自产出函数声明的返回类型）供黑板/报告展示。`object` SHALL 接受任意对象值（不校验具体类型）；对象在报告 / 黑板中按 `repr` 截断展示（防超长）。语义类型（金额/订单号/URL/日期 等）不占类型位，本质为 str/float 等基础类型。

#### Scenario: 合法类型值写入成功

- **WHEN** 块声明变量类型为 `float` 并写入合法数值
- **THEN** 写入成功且校验通过

#### Scenario: 泛型对象值写入

- **WHEN** 块声明变量类型为 `object` 并写入插件对象（页面对象 / 会话 / 文件句柄）
- **THEN** 写入成功（不校验具体类型），黑板/报告以 `str(value)` 呈现，并记录实际类型

#### Scenario: 非法类型值写入被拒绝

- **WHEN** 块声明变量类型为 `float` 并写入非数值文本
- **THEN** 系统拒绝写入并触发断言失败，终止当前流程

#### Scenario: 提取时类型转换与校验

- **WHEN** 块读取声明为 `float` 的变量，而其存储值不符合 float 类型（如无法转换的文本）
- **THEN** 系统在提取/写入时触发断言失败，终止当前流程

#### Scenario: 声明类型时 coerce 转换

- **WHEN** 目标变量已声明类型（非空 token）且提取值可转换（如 `"42"` 配 `int`）
- **THEN** 系统 coerce 后存储真实 Python 类型（int 42），而非原样存字符串

## REMOVED Requirements

### Requirement: 页面变量机制

**Reason**: 页面概念归浏览器插件，不再是引擎内置特殊类型；`page_ref` 泛型化为 `object` 类型（浏览器插件的对象），只有使用浏览器插件才涉及页面对象。
**Migration**: 页面对象作为泛型对象值在变量中存储与传递（与普通参数一致）；当前活动页由浏览器插件内部维护；引擎核心不再有 `page_ref` / `current_page` / 页面变量概念。
