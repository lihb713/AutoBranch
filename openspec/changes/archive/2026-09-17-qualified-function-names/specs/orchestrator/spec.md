## MODIFIED Requirements

### Requirement: FunctionCall 节点执行

编排器 SHALL 在执行遍历到 FunctionCall 节点时**确定性调用**：按**全名**经插件框架分发调用（不经 LLM），实参从当前帧求值（元素与 ref `args` 同构：本树裸变量名或字面量）、返回值按节点 `returns` 回收进当前帧。实参求值失败（如未定义变量）、函数执行失败（含异常）SHALL 使该节点 FAILURE，失败原因含函数全名与错误。

#### Scenario: 直接调用函数并回收返回值
- **WHEN** 遍历到 FunctionCall 节点（`function` / `args` / `returns`，`function` 为全名）
- **THEN** 引擎按全名调用插件函数，返回值写入 `returns` 目标变量

#### Scenario: 函数执行失败
- **WHEN** FunctionCall 调用的函数抛异常或返回失败
- **THEN** 该节点 FAILURE，失败原因含函数全名与错误

### Requirement: 插件分发与懒装配

编排器 SHALL 经插件框架统一分发调用：按**全名**定位所属插件 → 若未装配则懒装配（调用插件 `init`）→ 调用（向插件传裸函数名）→ 产出型工具由引擎落笔写变量。重资源插件（如浏览器）SHALL 在单次运行内首次用到才启动、运行结束（含失败 / 异常提前终止）统一释放，释放逻辑保证提前终止时仍执行。

#### Scenario: 首次调用触发懒装配
- **WHEN** 行为树首次调用某重资源插件的函数（全名）
- **THEN** 引擎装配该插件依赖并启动资源，随后执行调用

#### Scenario: 运行结束释放资源
- **WHEN** 行为树运行结束
- **THEN** 已启动的重资源（浏览器等）统一释放