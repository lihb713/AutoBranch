# behavior-tree-parser Specification

## Purpose

将用户书写的行为树文档（yaml/dict）确定性解析为仅含基础节点的内部行为树对象，展开复合节点、解析块引用、提取 schema 绑定声明并执行清晰度校验，作为书写层与执行层的唯一转换点。

## Requirements

### Requirement: 行为树文档解析
系统 SHALL 接受一份行为树文档（yaml/dict，含 block 定义与根流程）作为输入，解析为内部行为树对象（`BehaviorTree`），其中节点仅为基础节点类型（Action / Condition / Sequence / Selector / Repeat / Finish）。解析过程 MUST 是纯逻辑的：不依赖 LLM、不依赖浏览器、不产生外部副作用。解析入口 MUST 同时返回块声明表与清晰度校验报告（`ParseResult`）。

#### Scenario: 合法文档解析为基础节点行为树
- **WHEN** 输入一份合法行为树文档（包含命名块定义与根流程）
- **THEN** 系统返回内部行为树对象，节点全部为基础节点，块声明表包含每个命名块的输入/输出声明，校验报告显示通过

#### Scenario: 非 yaml/dict 输入返回错误
- **WHEN** 输入既不是合法 yaml 也不是合法 dict 的文档源
- **THEN** 系统在解析入口抛出可识别的解析错误，且不产生部分行为树结果

#### Scenario: 同一输入确定性输出
- **WHEN** 对同一份文档以相同解析参数调用两次
- **THEN** 两次返回的行为树对象结构完全一致（确定性）
### Requirement: 复合节点展开
系统 SHALL 在解析时确定性展开全部复合节点为仅含基础节点的组合，使展开后的行为树不含任何复合节点。各复合节点的展开语义 MUST 严格符合契约：`Step = Sequence(Action + Condition)`；`Branch = Action + Selector`（按顺序检查 `when`，第一个命中生效，无匹配走 `otherwise`）；`LoopUntil = Repeat(mode=loop_until, until=条件, max=上界)`；`Retry = Repeat(mode=retry, max=上界)`（终止条件为子节点执行结果）；`IfThenElse = Selector(if→then, else→else)`。

#### Scenario: Step 展开为 Sequence(Action + Condition)
- **WHEN** 文档中出现 `Step: { action, expect }`
- **THEN** 展开为 `Sequence` 节点，其第一个子节点为 `Action`（含自然语言描述与可选 CSS 提示），第二个子节点为 `Condition`（验证条件）

#### Scenario: Branch 展开为 Action + Selector
- **WHEN** 文档中出现带多个 `when` 分支与 `otherwise` 的 `Branch`
- **THEN** 展开为 `Action` 后接 `Selector`，`Selector` 按书写顺序检查各分支 `when` 条件，第一个匹配即生效，无匹配时走 `otherwise` 分支

#### Scenario: LoopUntil 展开为 Repeat(loop_until)
- **WHEN** 文档中出现 `LoopUntil: { action, until, max }`
- **THEN** 展开为 `Repeat` 节点，`mode=loop_until`，每轮先判 `until` 条件、不满足才执行循环体，达到 `max` 仍不满足则整体失败（安全闸）

#### Scenario: Retry 展开为 Repeat(retry)
- **WHEN** 文档中出现 `Retry: { max, body }`
- **THEN** 展开为 `Repeat` 节点，`mode=retry`，每轮直接执行 `body`，`body` 成功即退出，失败则重试，达到 `max` 仍失败则整体失败

#### Scenario: IfThenElse 展开为 Selector
- **WHEN** 文档中出现 `IfThenElse: { if, then, else }`
- **THEN** 展开为 `Selector`，先判 `if` 条件走 `then` 分支，否则走 `else` 分支
### Requirement: 块引用解析
系统 SHALL 解析行为树文档中的块引用（`ref:`），支持 `this/块名`（当前文档内命名块）、`文档名/块名`（跨文档引用某块）、`文档名/文档名`（跨文档引用整个行为树，因根块名即文档名）。跨文档解析 MUST 通过解析入口传入的引用解析器加载引用文档，且 MUST 在目标块不存在时判定校验失败。引用 MUST 保留为调用节点 `RefNode`（不内联展开），并为每个被引用块预展开可执行基础树（`blocks_tree`，块名 → 基础树，含根块与全部命名块，跨文档同名块以 `文档/块` 收纳），供运行期（M7）动态调用与参数绑定/可见性校验使用。

#### Scenario: 引用当前文档命名块
- **WHEN** 文档中出现 `ref: this/登录`
- **THEN** 系统在当前文档块声明表中找到 `登录` 块，生成 `RefNode`（目标 `this/登录`），并将 `登录` 块预展开树放入 `blocks_tree`

#### Scenario: 跨文档引用命名块
- **WHEN** 文档中出现 `ref: 登录/登录`
- **THEN** 系统通过引用解析器加载 `登录` 文档，引用其根块（即整个行为树），生成 `RefNode`（目标 `登录/登录`），并将该树放入 `blocks_tree`（键 `登录/登录`）

#### Scenario: 引用不存在的块
- **WHEN** 文档中出现指向不存在文档或不存在块名的 `ref:`
- **THEN** 系统清晰度校验判定引用不存在，校验报告包含指明缺失目标的可读错误
### Requirement: schema 绑定声明提取
系统 SHALL 从每个命名块（含根块）的接口声明中提取输入/输出声明，构成块声明表（`blocks`），供下游 schema 命名空间建立使用。声明的输入 MUST 作为调用方需注入的参数、输出 MUST 作为调用方可读取的返回值，变量名 MUST 严格对应块接口声明。解析时 SHALL 在块引用位置记录 args/returns 绑定关系（`args` 传实参、`returns` 接收输出）。

#### Scenario: 提取命名块输入输出声明
- **WHEN** 文档中命名块声明了 `inputs` 与 `outputs`
- **THEN** 块声明表包含该块的输入参数列表与输出参数列表，供后续 schema 命名空间建立

#### Scenario: 块引用处记录参数绑定
- **WHEN** 一个块引用另一块并在引用处书写了 `args`/`returns` 参数绑定
- **THEN** 系统将该绑定记录为对被引用块独立 schema 的输入注入（`args`）与输出接收（`returns`），绑定变量名与块输入/输出声明一致
### Requirement: 配置参数覆盖声明识别
系统 SHALL 识别块 schema 下声明的配置参数覆盖（如 timeout / retry 等），工具定义的配置参数名称与语义固定，用户不在文档中书写全局配置；覆盖值只在当前块及其子树内生效，未定义时向上查找祖先，最终回落到全局默认。系统 MUST 将识别出的配置参数覆盖随块声明一并输出，供执行层解析配置生效范围。

#### Scenario: 识别块内配置参数覆盖
- **WHEN** 命名块的 schema 下声明了同名配置参数（如 `timeout`）及覆盖值
- **THEN** 系统将其识别为配置参数覆盖并纳入块声明，标注生效范围为该块及其子树

#### Scenario: 未定义配置参数时使用全局默认
- **WHEN** 文档中任何块都未声明某配置参数
- **THEN** 系统不要求用户在文档中书写该参数，解析输出不包含该参数的覆盖，实际取值回落至全局默认（执行层处理）
### Requirement: 清晰度校验（结构与展开合法性）
系统 SHALL 在解析时执行清晰度校验，检查行为树结构合法（节点类型正确、嵌套关系有效）且复合节点展开后合法（展开为基础节点后可被遍历）。结构非法或展开后非法的文档 MUST 校验失败并返回错误。

#### Scenario: 非法节点类型被判失败
- **WHEN** 文档中出现未定义的节点类型或非法嵌套关系
- **THEN** 校验失败，报告指明非法位置与原因

#### Scenario: 展开后结构合法则通过
- **WHEN** 文档含复合节点且其展开后的基础节点组合可被正常遍历
- **THEN** 结构类校验通过
### Requirement: 清晰度校验（引用与循环上界）
系统 SHALL 校验所有块引用存在（`ref:` 指向的块/文档可解析），且循环均有上界（`max`）。引用不存在或循环无上界的文档 MUST 校验失败。

#### Scenario: 引用缺失被判失败
- **WHEN** `ref:` 指向不存在的块或文档
- **THEN** 校验失败，报告包含缺失目标的可读错误

#### Scenario: 循环无上界被判失败
- **WHEN** LoopUntil / Retry 等循环结构未声明 `max`
- **THEN** 校验失败，报告指明缺少循环上界的节点
### Requirement: 清晰度校验（变量契约）
系统 SHALL 校验变量契约一致：引用的变量在其可见作用域内（每块只读写自己的 schema 的 `this/<名>` 单段，不访问直接子块/祖先/兄弟/孙子 schema）。越作用域引用的变量 MUST 校验失败。

#### Scenario: 变量引用在作用域内则通过
- **WHEN** 变量引用指向自己的 schema（`this/<名>` 单段）
- **THEN** 变量契约校验通过

#### Scenario: 变量越作用域被判失败
- **WHEN** 变量引用指向祖先、兄弟或孙子级别的 schema
- **THEN** 校验失败，报告指明越作用域的变量引用位置

#### Scenario: 读取未定义变量被判失败
- **WHEN** 块内 `Param.x` 读取的变量既非本块 `inputs` 声明、也非块内 `NewParam.x` 目标或 ref `returns` 目标
- **THEN** 校验失败，报告含 `scope.get_undeclared`（output 声明不构成读取源）
### Requirement: 清晰度校验（主块名强制与输出全赋值）
系统 SHALL 校验主块名必须等于行为树名（文档名），不匹配时校验失败（`structure.missing_main_block`）；块声明的每个 `outputs` 名 MUST 在块体内存在赋值点（叶子 `NewParam.<名>` 或本块 ref 的 `returns` 目标），否则校验失败（`ref.output_not_set`）。

#### Scenario: 主块名不等于行为树名被判失败
- **WHEN** 文档中主块名与行为树名不一致
- **THEN** 校验失败，报告含 `structure.missing_main_block`

#### Scenario: 输出未赋值被判失败
- **WHEN** 块声明了 `outputs` 但块体内既无对应 `NewParam.<输出>` 也无 ref `returns` 目标为其赋值
- **THEN** 校验失败，报告含 `ref.output_not_set`
### Requirement: 清晰度校验（可定位与验证条件）
系统 SHALL 校验每条动作目标可定位（有 CSS 提示或有 LLM 可映射的自然语言描述）且每步有验证条件（Step/Branch 等的 expect/判断），否则该步成败无法判定。动作不可定位或缺少验证条件的文档 MUST 校验失败。

#### Scenario: 动作可定位则通过
- **WHEN** Action 节点含 CSS 提示或足够的自然语言描述
- **THEN** 可定位性校验通过

#### Scenario: 动作不可定位被判失败
- **WHEN** Action 节点既无 CSS 提示也无 LLM 可映射的自然语言描述
- **THEN** 校验失败，报告指明不可定位的动作

#### Scenario: 缺少验证条件被判失败
- **WHEN** Step / Branch 等步骤缺少 `expect` 或判断条件
- **THEN** 校验失败，报告指明缺少验证条件的步骤
### Requirement: 清晰度校验（条件谓词结构可校验）
系统 SHALL 校验所有条件谓词结构可校验（判断可由 LLM 结合语义图完成，如条件指向的页面对象存在、比较目标可解析）。条件谓词结构不可校验的文档 MUST 校验失败。

#### Scenario: 条件谓词可解析则通过
- **WHEN** 条件谓词指向可解析的页面对象与可比较目标
- **THEN** 谓词校验通过

#### Scenario: 条件谓词不可校验被判失败
- **WHEN** 条件谓词指向无法解析的对象或目标
- **THEN** 校验失败，报告指明不可校验的谓词
### Requirement: 校验报告输出
系统 SHALL 输出清晰度校验报告（`CheckReport`），包含整体通过/失败结论与错误清单。校验失败时错误清单 MUST 逐条可读、可定位到文档位置并指明违反规则，供返回用户修正。

#### Scenario: 校验通过输出通过结论
- **WHEN** 文档全部校验项通过
- **THEN** 报告结论为通过，错误清单为空

#### Scenario: 校验失败输出可读错误清单
- **WHEN** 文档存在一类或多类校验违规
- **THEN** 报告结论为失败，错误清单逐条列出违规、对应文档位置与违反的校验规则
### Requirement: FunctionCall 节点解析

系统 SHALL 解析函数调用节点（`type: function`）：`function`（**全名标识** `插件名.函数名`，如 `compute.add`）+ `args`（实参列表，按序对应函数入参）+ `returns`（字典，本树接收名 → 类型，按序对应函数多返回值）。FunctionCall 节点 SHALL 保留为运行期调用节点（不展开），由分发层在运行期按全名调用插件函数：实参从当前帧求值、返回值按 `returns` 回收进当前帧。实参元素 SHALL 与 ref `args` 同构（本树裸变量名或字面量）；求值失败（如未定义变量）由运行期处理为节点 FAILURE。函数不存在或参数与函数签名不匹配时，清晰度校验 SHALL 判定失败；函数存在性校验 SHALL 基于校验时点的注册表（按全名），运行期函数缺失（插件被删 / 重载）时 FunctionCall 节点 FAILURE（与编排器语义一致）。

#### Scenario: 合法 FunctionCall 节点解析
- **WHEN** 文档中出现 `type: function`（含 `function` / `args` / `returns`，`function` 为全名）
- **THEN** 解析为函数调用节点（保留 function / args / returns），校验通过

#### Scenario: 函数不存在
- **WHEN** `function` 指向未注册的全名函数
- **THEN** 清晰度校验判定失败，报告指明缺失函数

#### Scenario: args 与函数签名对齐
- **WHEN** `args` 数量 / 类型与函数入参声明不匹配
- **THEN** 清晰度校验判定参数不匹配，报告指明问题
### Requirement: 容器类型与泛型类型

文档级 `inputs` / `outputs` 与 `returns` 的类型 token SHALL 支持基本容器类型 `array`（list）、`object`（dict）、不确定类型 `generics` 与自定义 `page_ref`（除 `str` / `int` / `float` / `bool` 外）。`generics` 用于承载页面对象/会话/文件句柄等无法归类的值，解析层只校验 token 已登记。

#### Scenario: 声明容器与泛型类型参数
- **WHEN** 文档声明 `inputs: {items: array, payload: object, 会话: generics}`
- **THEN** 解析通过，类型 token 合法


### Requirement: FunctionCall 命名参数

FunctionCall SHALL 支持位置参数 `args` 与命名参数 `kwargs`。`args` 按函数参数声明顺序映射；`kwargs` 以参数名为键，可跳过中间可选参数。命名参数值 SHALL 支持字面量、`Param.x` 与嵌套 dict/list（字符串叶子按字面量/变量规则求值）。校验 SHALL 拒绝未知/重复命名参数与缺失必填参数。

#### Scenario: 跳过中间可选参数

- **WHEN** 调用 `ssh.create_session(host=..., jump={host: ...})` 且不提供 key/timeout/proxy
- **THEN** 校验通过，运行时只传入 host 与 jump，其余参数使用函数默认值

#### Scenario: 命名参数嵌套对象

- **WHEN** `kwargs.jump = {host: jump.internal, user: ops}`
- **THEN** 运行时把该对象传给函数，字符串叶子按需支持变量求值

#### Scenario: 重复/未知命名参数

- **WHEN** `kwargs` 指定了函数不存在的参数，或与位置参数重复
- **THEN** 保存校验返回 422


### Requirement: ForEach 节点

行为树 SHALL 支持 `ForEach` 节点：`variables` 定义临时变量（列表值逐项取元素，非列表值每轮同值）、`body` 槽位、`on_failure`（continue/abort）。系统 SHALL 校验变量名、body 存在与策略合法；列表变量长度不一致时运行期失败。

#### Scenario: 遍历列表
- **WHEN** `variables.env_id` 是 `["a","b"]` 的列表值
- **THEN** body 依次在临时子帧中执行 2 次，每轮 `Param.env_id` 分别为 a/b

#### Scenario: 失败策略
- **WHEN** 单轮 body 失败且 `on_failure=continue`
- **THEN** 跳过该轮继续；`abort` 时立即返回失败

### Requirement: 条件模式与谓词表达式

条件字段 SHALL 支持显式 `mode`：`natural` 使用单行 `text`；`predicate` 使用 `expression`。谓词表达式 SHALL 支持 `function/args/kwargs` 叶子与嵌套 `all` / `any` / `not` 组；自然语言不可与谓词混用。空 `all/any`、多子项 `not`、未知 mode MUST 校验失败。谓词函数 MUST 用户可见、恰好单返回 `bool`。

#### Scenario: 谓词表达式解析
- **WHEN** IfThenElse.if 使用 mode=predicate 且 expression 为嵌套 all/any/not
- **THEN** 解析通过，函数/参数校验在 checks 阶段执行

#### Scenario: 空组拒绝
- **WHEN** all 或 any 为空列表
- **THEN** 返回 invalid_expression 校验错误


### Requirement: Parallel 节点解析

系统 SHALL 解析 Parallel 节点：`variables`/`body`/`on_failure` 与 ForEach 同构，并支持正整数 `max_concurrency` 与 `on_conflict`（error/last）。

#### Scenario: 解析并发遍历
- **WHEN** 文档包含 Parallel 节点
- **THEN** 输出 ParallelNode 并校验变量与并发策略
