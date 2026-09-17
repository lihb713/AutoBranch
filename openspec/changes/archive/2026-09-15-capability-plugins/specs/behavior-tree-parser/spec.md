## ADDED Requirements

### Requirement: FunctionCall 节点解析

系统 SHALL 解析函数调用节点（`type: function`）：`function`（注册函数名）+ `args`（实参列表，按序对应函数入参）+ `returns`（字典，本树接收名 → 类型，按序对应函数多返回值）。FunctionCall 节点 SHALL 保留为运行期调用节点（不展开），由分发层在运行期按函数名调用插件函数：实参从当前帧求值、返回值按 `returns` 回收进当前帧。实参元素 SHALL 与 ref `args` 同构（本树裸变量名或字面量）；求值失败（如未定义变量）由运行期处理为节点 FAILURE。函数不存在或参数与函数签名不匹配时，清晰度校验 SHALL 判定失败；函数存在性校验 SHALL 基于校验时点的注册表，运行期函数缺失（插件被删 / 重载）时 FunctionCall 节点 FAILURE（与编排器语义一致）。

#### Scenario: 合法 FunctionCall 节点解析
- **WHEN** 文档中出现 `type: function`（含 `function` / `args` / `returns`）
- **THEN** 解析为函数调用节点（保留 function / args / returns），校验通过

#### Scenario: 函数不存在
- **WHEN** `function` 指向未注册的函数
- **THEN** 清晰度校验判定失败，报告指明缺失函数

#### Scenario: args 与函数签名对齐
- **WHEN** `args` 数量 / 类型与函数入参声明不匹配
- **THEN** 清晰度校验判定参数不匹配，报告指明问题

### Requirement: 泛型对象类型

文档级 `inputs` / `outputs` 与 `returns` 的类型 token SHALL 支持泛型对象类型 `object`（除 `str` / `int` / `float` / `bool` 外）。`object` 用于承载插件对象（页面对象 / 会话 / 文件句柄…），解析层对其不做具体类型校验。

#### Scenario: 声明 object 类型参数
- **WHEN** 文档声明 `inputs: {会话: object}` 或 `returns: {会话: object}`
- **THEN** 解析通过，类型 token 合法
