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
系统 SHALL 解析行为树文档中的块引用（`ref:`），支持 `this/块名`（当前文档内命名块）、`文档名/块名`（跨文档引用某块）、`文档名/文档名`（跨文档引用整个行为树，因根块名即文档名）。跨文档解析 MUST 通过解析入口传入的引用解析器加载引用文档，且 MUST 在目标块不存在时判定校验失败。解析引用 MUST 同步建立该引用的独立 schema 命名空间（类似调用栈帧），作为参数绑定与可见性校验的基础。

#### Scenario: 引用当前文档命名块
- **WHEN** 文档中出现 `ref: this/登录`
- **THEN** 系统在当前文档块声明表中找到 `登录` 块，并将其子树内联到引用位置，且为该引用建立独立 schema 命名空间

#### Scenario: 跨文档引用命名块
- **WHEN** 文档中出现 `ref: 登录/登录`
- **THEN** 系统通过引用解析器加载 `登录` 文档，引用其根块（即整个行为树），并建立独立 schema 命名空间

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
系统 SHALL 校验变量契约一致：引用的变量在其可见作用域内（每块只读写自己的 schema 与直接子块的 schema，不访问祖先/兄弟/孙子 schema）。越作用域引用的变量 MUST 校验失败。

#### Scenario: 变量引用在作用域内则通过
- **WHEN** 变量引用指向自己的 schema 或直接子块的 schema
- **THEN** 变量契约校验通过

#### Scenario: 变量越作用域被判失败
- **WHEN** 变量引用指向祖先、兄弟或孙子级别的 schema
- **THEN** 校验失败，报告指明越作用域的变量引用位置

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