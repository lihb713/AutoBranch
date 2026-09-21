# orchestrator Specification

## Purpose

定义 AutoBranch 引擎的确定性编排与遍历契约：行为树的阻塞式遍历、SUCCESS/FAILURE 聚合与短路、组合节点纯程序执行、叶子触发与失败传播、schema 帧生命周期、会话初始化、全局超时以及可查询的执行状态，是引擎整合 M2/M3/M6/M8 并对外（M9b）提供 `engine.run` 与执行状态轮询的唯一中枢。

## Requirements

### Requirement: 引擎运行入口

系统 SHALL 提供 `engine.run(tree, blocks, config)` 入口，接收内部行为树、块声明表与运行配置，完成会话初始化后对行为树执行一次确定性遍历。运行入口 SHALL 支持接收**根级入参值**（按文档 `inputs` 声明类型 coerce 后注入根帧，叶子以 `Param.<名>` 读取）并在运行结束后返回**出参**（按文档 `outputs` 声明读根帧输出）。运行结束后系统 SHALL 返回运行结果，包含最终状态（`success` / `failure`）、失败原因（失败时非空）、出参、执行报告与回溯报告。当行为树解析/校验失败时，系统 SHALL 返回可供修正的错误信息，且不启动任何遍历。

#### Scenario: 行为树整体执行成功

- **WHEN** 调用方以合法行为树、块声明与配置调用 `engine.run`
- **THEN** 系统返回状态为 `success` 的运行结果，失败原因为空，且附带完整的执行报告与回溯报告

#### Scenario: 叶子失败导致整体失败并携带原因

- **WHEN** 行为树中某叶子节点执行失败并沿树传播到根
- **THEN** 系统返回状态为 `failure` 的运行结果，失败原因指向该叶子节点，并附带完整的执行报告与回溯报告

#### Scenario: 校验失败不启动遍历

- **WHEN** 调用方传入无法通过清晰度校验的行为树（如块引用不存在、循环无上界）
- **THEN** 系统返回校验失败的错误信息，不启动任何节点遍历，也不产出执行报告

#### Scenario: 根级入参按声明类型注入

- **WHEN** 调用方以根级入参值（如 `{"user": "admin"}`）调用 `engine.run`，且文档 `inputs` 声明了对应类型
- **THEN** 系统按声明类型 coerce 后注入根帧，叶子以 `Param.user` 读取到该值

#### Scenario: 运行结束返回出参

- **WHEN** 行为树运行结束且根帧写入了 `outputs` 声明的出参
- **THEN** 运行结果包含出参值（按声明名读取根帧输出）
### Requirement: 阻塞式遍历语义

系统 SHALL 以阻塞式方式遍历行为树：一个节点执行完成后才执行下一个节点，节点状态只有 `SUCCESS` / `FAILURE` 两种，不存在 `RUNNING` 中间状态。系统 SHALL 按树结构从上到下、从左到右遍历全部节点，且每次运行对同一行为树产生确定的遍历结果。

#### Scenario: 节点串行执行无并发

- **WHEN** 系统遍历一个包含多个子节点的行为树
- **THEN** 同一时刻至多有一个节点处于执行中，前一个节点已返回 SUCCESS 或 FAILURE 后，下一个节点才开始执行

#### Scenario: 节点仅返回成功或失败

- **WHEN** 任意节点（叶子或组合节点）执行结束
- **THEN** 其返回状态必然是 `SUCCESS` 或 `FAILURE` 二者之一，不出现第三种状态
### Requirement: Sequence 顺序执行与短路

系统 SHALL 按声明顺序依次执行 Sequence 的子节点；任一子节点返回 FAILURE 时，该 Sequence 立即短路为整体 FAILURE，且后续子节点不再执行；仅当所有子节点均返回 SUCCESS 时，Sequence 才返回 SUCCESS。

#### Scenario: 全部子节点成功

- **WHEN** Sequence 的全部子节点依次返回 SUCCESS
- **THEN** Sequence 返回 SUCCESS，且所有子节点均被执行

#### Scenario: 中途失败短路

- **WHEN** Sequence 的第 N 个子节点返回 FAILURE，其后还有待执行子节点
- **THEN** Sequence 立即返回 FAILURE，且第 N 个之后的子节点均不执行
### Requirement: Selector 按条件分流

系统 SHALL 按声明顺序检查 Selector 的子节点（分支）；第一个返回 SUCCESS 的分支生效，该 Selector 立即短路为整体 SUCCESS，其余分支不再执行；仅当所有分支均返回 FAILURE 时，Selector 才返回 FAILURE。Selector 语义严格限定为"按条件选路径"，不承载兜底语义。

#### Scenario: 首个成功分支生效

- **WHEN** Selector 的第 M 个分支返回 SUCCESS，其后还有待检查分支
- **THEN** Selector 返回 SUCCESS，且第 M 个之后的分支均不执行

#### Scenario: 全部分支失败

- **WHEN** Selector 的所有分支均返回 FAILURE
- **THEN** Selector 返回 FAILURE，不落入任何分支路径
### Requirement: Repeat 循环带上限

系统 SHALL 循环执行 Repeat 的子节点，并携带循环上界（`max`）；当循环到达上界仍未满足退出条件时，Repeat 返回 FAILURE（安全闸，防死循环）。Repeat 支持两种模式，其退出条件检查时机不同。

#### Scenario: 达到上界返回失败

- **WHEN** Repeat 循环次数到达 `max` 上界且退出条件始终未满足
- **THEN** Repeat 返回 FAILURE，循环不再继续

#### Scenario: 满足条件提前退出

- **WHEN** Repeat 在某轮循环后退出条件得到满足
- **THEN** Repeat 返回 SUCCESS，循环在到达上界前结束
### Requirement: LoopUntil 先判 until 条件

系统 SHALL 在 LoopUntil 模式的每一轮循环开头先求值 `until` 页面条件：条件已满足 → 退出循环并返回 SUCCESS；条件不满足 → 执行循环体后进入下一轮。循环体不会在条件已满足时执行。

#### Scenario: 条件初始即满足

- **WHEN** LoopUntil 第一轮开始时 `until` 条件已满足
- **THEN** 系统返回 SUCCESS，且循环体一次也不执行

#### Scenario: 条件不满足时执行循环体

- **WHEN** LoopUntil 某轮开始时 `until` 条件不满足
- **THEN** 系统执行该轮循环体，循环体执行完毕后进入下一轮检查
### Requirement: Retry 后判 body 结果

系统 SHALL 在 Retry 模式下每轮直接执行循环体：循环体返回 SUCCESS → 立即退出并返回 SUCCESS；循环体返回 FAILURE → 重试执行循环体；到达 `max` 上界仍失败 → 整体返回 FAILURE。Retry 的终止条件来自子节点执行结果，而非页面条件。

#### Scenario: body 成功即退出

- **WHEN** Retry 的循环体在某一轮执行返回 SUCCESS
- **THEN** Retry 立即返回 SUCCESS，不再继续执行循环体

#### Scenario: body 失败重试直至上限

- **WHEN** Retry 的循环体连续执行失败，且失败轮次到达 `max` 上界
- **THEN** Retry 返回 FAILURE，重试结束
### Requirement: 叶子节点触发执行

系统 SHALL 在遍历到 Action / Condition 叶子节点时调用叶子执行（M6），将节点描述等上下文提供给叶子执行接口，并接收其返回结果（状态、Condition 布尔值、错误来源、执行追踪数据）作为该叶子节点的状态依据。系统 SHALL 记录叶子返回的执行追踪数据以供回溯报告使用。

#### Scenario: Action 叶子返回成功

- **WHEN** 系统触发一个 Action 叶子执行，且叶子返回 `success`
- **THEN** 该叶子节点状态为 SUCCESS，其追踪数据被记录且进入对应节点报告

#### Scenario: Condition 叶子布尔结果映射状态

- **WHEN** 系统触发一个 Condition 叶子执行，且叶子返回布尔值
- **THEN** 该叶子节点状态按布尔值映射为 SUCCESS 或 FAILURE，布尔值与追踪数据均进入对应节点报告

#### Scenario: 叶子失败沿树传播

- **WHEN** 某叶子节点执行返回 FAILURE
- **THEN** 该失败状态沿行为树向上传播，由其父组合节点按聚合规则处理，最终由根统一决定终止
### Requirement: schema 帧生命周期

系统 SHALL 在每次 ref 动态调用（RefNode）时通过 schema 命名空间（M3）建立独立子帧（如 `T/登录/`）：在父帧求值 `args` 实参（`this/<名>` 或字面量）并 coerce 到输入类型，`enter_block` 建子帧并注入形参；子块 SUCCESS 后按 `returns` 读子帧输出写回父帧，随后 `exit_block` 退出子帧。帧数据保留至整个行为树运行结束（供黑板上报），运行期访问由激活帧控制。多个块引用产生的帧互不干扰，同名变量在不同帧中不冲突。配置参数按"自己的 schema → 祖先 → 全局默认"的规则解析。

#### Scenario: 块引用建立独立帧

- **WHEN** 系统遍历到一个 ref 调用节点（RefNode）
- **THEN** 系统求值并注入 args 实参后为该引用建立独立 schema 子帧，子块内变量读写限定在该帧（`this/<名>` 单段）范围内

#### Scenario: 块退出释放帧

- **WHEN** 一个块引用（RefNode 动态调用）执行完毕（无论 SUCCESS 或 FAILURE）并退出
- **THEN** 系统退出该子帧（SUCCESS 时已按 `returns` 回收输出到父帧），帧数据保留至运行结束供黑板上报，不再作为激活帧参与寻址

#### Scenario: 同名变量互不冲突

- **WHEN** 两个不同的块引用内部各自写入同名变量（如均含 `username`）
- **THEN** 两个变量分别存在于各自的 schema 帧中，互不覆盖、互不干扰

#### Scenario: 配置参数向上继承

- **WHEN** 某块自身的 schema 未定义某个配置参数（如 timeout）
- **THEN** 系统沿"块自身 → 最近祖先 → 全局默认"的顺序解析出该参数的有效值
### Requirement: 会话初始化

系统 SHALL 在每次 `engine.run` 开始时初始化会话：创建全新的浏览器 context（从 0 开始、无历史 cookie/登录态、不持久化），并将全局默认配置注入根级 schema。全流程共享这一个 context，且整个行为树执行结束后统一释放浏览器会话。

#### Scenario: 每次运行全新会话

- **WHEN** 系统开始一次 `engine.run`
- **THEN** 系统创建一个全新的浏览器 context，不包含任何历史 cookie 或登录态，全流程共享该 context

#### Scenario: 全局配置注入根级 schema

- **WHEN** 系统初始化会话
- **THEN** 全局默认配置（timeout/retry/浏览器等）被注入根级 schema，作为配置参数继承链的最终兜底

#### Scenario: 执行结束释放会话

- **WHEN** 行为树遍历结束（无论成功或失败）
- **THEN** 系统释放本次运行创建的浏览器 context，运行之间不残留任何会话状态
### Requirement: 可查询执行状态

系统 SHALL 在遍历过程中持续维护可查询的执行状态，包含运行标识（run_id）、进度（0.0 ~ 1.0）、当前正在执行的节点、已完成节点的报告列表，以及运行是否结束的标记。系统 SHALL 在执行期间任意时刻提供该状态的查询接口，供 M9b 轮询；进度与已完成节点报告随节点执行实时更新，全部节点结束后运行标记为已结束。

#### Scenario: 执行中状态实时更新

- **WHEN** 系统正在遍历行为树，且调用方查询执行状态
- **THEN** 返回的状态包含当前进度、正在执行的节点信息与截至当前的已完成节点报告，进度随执行单调推进

#### Scenario: 节点完成累积到已完成列表

- **WHEN** 行为树中任一节点执行完毕
- **THEN** 该节点的报告被追加到执行状态的已完成节点报告列表中，当前节点推进到下一个待执行节点

#### Scenario: 运行结束状态置为已结束

- **WHEN** 行为树遍历结束（成功或失败）
- **THEN** 执行状态标记运行已结束，已完成节点报告列表包含全部节点的报告
### Requirement: 全局超时

系统 SHALL 使全局 timeout 在节点层面生效：任一叶子节点执行超时即终止该叶子，并将其记为失败（LLM 侧失败）沿树传播。超时以运行配置中的全局值作为默认，允许按配置继承规则被覆盖。

#### Scenario: 单叶子超时终止

- **WHEN** 某叶子节点执行时长超过其生效的 timeout 值仍未返回
- **THEN** 系统终止该叶子执行，将其状态置为 FAILURE，并沿树传播该失败

#### Scenario: 超时值按配置继承生效

- **WHEN** 某叶子节点所在块通过 schema 覆盖了 timeout 配置
- **THEN** 该叶子使用覆盖后的 timeout 值判定是否超时，其他未覆盖块中的叶子仍使用全局默认值
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
