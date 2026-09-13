## MODIFIED Requirements

### Requirement: 行为树文档解析（一文档一树 + 统一槽位模型）

系统 SHALL 接受一份行为树文档（yaml/dict，一文档一树）作为输入，解析为内部行为树对象（`BehaviorTree`）。文档结构：`tree: <名>`（树名=文档名）+ 可选文档级 `inputs`/`outputs`（接口声明，`inputs` 值为类型 token：str/int/float/bool/page_ref）+ 可选全局配置（`timeout`/`retry`/`browser` 保留名）+ `nodes:`（节点对象池平铺定义，每节点含 `id`/`type`/`name`/槽位字段/自有字段）+ `root: <id>`（指向 `type: Root` 节点）。

**统一槽位模型**：节点间的一切动作关联一律经槽位字段引用子树根节点 id。槽位字段按节点类型语义命名：

| 节点 | 槽位字段（值=子树根 id） | 自有字段 |
|---|---|---|
| Action（叶子） | — | `description`（操作描述） |
| Step | `action: id` | `expect`（验证条件） |
| Root | `body: id` | — |
| Sequence | `actions: [id, id]` | — |
| IfThenElse | `then: id`、`else: id` | `if`（判断条件） |
| Branch | `action: id`、`branches: [{when, action: id} \| {otherwise, action: id}]` | — |
| Retry | `body: id` | `max` |
| LoopUntil | `action: id` | `until`（终止条件）、`max` |
| ref（叶子） | — | `target`、`args`、`returns` |

Condition 为**概念性节点**（用户不可感知独立类型），内嵌为自有字段：`Step.expect`、`IfThenElse.if`、`Branch.branches[].when`、`LoopUntil.until`。

解析过程 MUST 是纯逻辑的：不依赖 LLM、不依赖浏览器、不产生外部副作用。解析入口 MUST 返回行为树、文档接口声明与清晰度校验报告。系统 SHALL 从 `root` 沿槽位引用构建主树；未被任何槽位引用的节点为游离树（允许出现在文档中）。

#### Scenario: 合法文档解析为基础节点行为树
- **WHEN** 输入一份含 `tree`/`nodes`/`root` 的一文档一树文档（含槽位引用的容器节点与 Action/ref 叶子）
- **THEN** 系统返回内部行为树（从 Root 起始）、文档级 inputs/outputs 声明与校验报告，校验通过；游离节点保留为游离树（不报错，允许草稿保存）

#### Scenario: 非 yaml/dict 输入返回错误
- **WHEN** 输入既不是合法 yaml 也不是合法 dict 的文档源
- **THEN** 系统在解析入口抛出可识别的解析错误，且不产生部分行为树结果

#### Scenario: 同一输入确定性输出
- **WHEN** 对同一份文档以相同解析参数调用两次
- **THEN** 两次返回的行为树对象结构完全一致（确定性）

### Requirement: 节点拓扑与必填校验

系统 SHALL 校验：槽位引用必须指向 `nodes` 中存在的节点（否则 `orphan_slot`）；同一节点不可被多个槽位引用（否则 `duplicate_reference`，破坏纯树结构）；主树与每棵游离树均无环（否则 `cycle`）；文档恰有一个 `type: Root` 节点且 `root` 引用指向它（否则 `single_root`/`bad_root`）；Root 固定 1 个槽位。

系统 SHALL 校验每节点必填字段：Action `description`；Step `action`+`expect`；IfThenElse `if`+`then`+`else`；Branch `action` + 至少一个分支（每分支 `when` 非空或为 `otherwise`）；Retry `body`+`max`；LoopUntil `until`+`action`+`max`；ref `target` 非空。

#### Scenario: 槽位引用校验
- **WHEN** 文档中槽位引用不存在的 id，或同一节点被多个槽位引用
- **THEN** 系统清晰度校验判定引用问题（孤儿引用/重复引用），报告指明节点

#### Scenario: 必填字段校验
- **WHEN** 某节点缺少其类型必填字段（如 Step 缺 action/expect、IfThenElse 缺 if/then/else）
- **THEN** 系统清晰度校验判定字段缺失，报告指明节点与字段

#### Scenario: 环校验
- **WHEN** 主树或某游离树存在槽位引用环
- **THEN** 系统清晰度校验判定环，报告指明起点

### Requirement: 引用解析（ref）

系统 SHALL 解析行为树文档中的引用节点（`ref:`）。**一文档一树下，引用目标为另一文档的整棵树**：`ref: 文档名`，运行时加载被引文档并从其 Root 节点执行。系统 SHALL 通过解析入口传入的引用解析器（`RefResolver`）按文档名加载被引文档，且 MUST 在目标文档不存在时判定校验失败。引用 MUST 保留为调用节点 `RefNode`（不内联展开）。

ref 参数对称：`args`（列表，按序对应被引树 `inputs`；元素为本树变量名 `this/<名>`/裸名或字面量 str/int/float/bool）与 `returns`（字典 `{本树接收名: 类型}`，按序对应被引树 `outputs`）。

#### Scenario: 引用目标文档
- **WHEN** 文档中出现 `ref: 文档B`
- **THEN** 系统按文档名经引用解析器加载文档B，生成 `RefNode`（目标 `文档B`），运行时从文档B的 Root 执行

#### Scenario: 引用不存在的文档
- **WHEN** `ref:` 指向不存在的文档
- **THEN** 系统清晰度校验判定引用不存在，报告指明缺失文档

#### Scenario: ref 参数对齐
- **WHEN** `ref:` 的 `args`/`returns` 与被引文档的 `inputs`/`outputs` 声明数量/顺序/类型不匹配
- **THEN** 系统清晰度校验判定参数不匹配，报告指明问题

#### Scenario: args 字面量传入
- **WHEN** `args` 元素不是本树已存在的变量名
- **THEN** 系统将其作为字面量（str/int/float/bool）传入，并校验与对应 `inputs` 声明的类型匹配

#### Scenario: 跨文档引用环校验
- **WHEN** 文档A引用文档B、B（直接或间接）又引用A
- **THEN** 系统清晰度校验判定跨文档循环引用，报告指明环路径

## REMOVED Requirements

### Requirement: 复合节点内联目标字段（then/else/body 目标字符串、branches 分支行）
**Reason**: 统一槽位模型取代——IfThenElse 的 then/else、Retry 的 body、Branch 的分支动作全部改为槽位字段引用子树根节点；Branch 的分支保留 `branches` 列表（`when`/`otherwise` 为条件字段、`action` 为槽位引用）。旧"目标字符串"（文档名或自然语言描述直接写在 then/else/body 字段）被移除。
**Migration**: 分支/循环体后续动作改为槽位引用子树根节点（如 `then: n5`）；纯单操作目标用 Action 叶子表达。

### Requirement: schema 绑定声明提取（多块形式）
**Reason**: 一文档一树取代多块模型，`blocks`（多块声明表）与 `this/块名` 同文档引用不再存在；块声明上移为文档级 `inputs`/`outputs`。
**Migration**: 文档级声明替代块声明；`ref: this/块` 改为 `ref: 文档名`；`blocks_tree` 语义变为"文档名→树"。