## MODIFIED Requirements

### Requirement: 行为树文档解析

系统 SHALL 接受一份行为树文档（yaml/dict，一文档一树）作为输入，解析为内部行为树对象（`BehaviorTree`）。文档结构为：`tree: <名>`（树名=文档名）+ 可选文档级 `inputs`/`outputs`（接口声明，`inputs` 值为类型 token：str/int/float/bool/page_ref，非法类型报错）+ 可选全局配置（`timeout`/`retry`/`browser` 保留名）+ `nodes:`（节点对象池平铺定义，每节点含 `id`/`type`/`name`/节点字段/`slots`）+ `root: <id>`（指向 `type: Root` 节点）。解析过程 MUST 是纯逻辑的：不依赖 LLM、不依赖浏览器、不产生外部副作用。解析入口 MUST 返回行为树、文档接口声明与清晰度校验报告。系统 SHALL 从 `root` 沿 `slots` 引用构建主树；未被任何 `slots` 引用的节点为游离树（允许出现在文档中）。

#### Scenario: 合法文档解析为基础节点行为树
- **WHEN** 输入一份含 `tree`/`nodes`/`root` 的一文档一树文档
- **THEN** 系统返回内部行为树（从 Root 起始）、文档级 inputs/outputs 声明与校验报告，校验通过；游离节点保留为游离树（不报错，允许草稿保存）

#### Scenario: 非 yaml/dict 输入返回错误
- **WHEN** 输入既不是合法 yaml 也不是合法 dict 的文档源
- **THEN** 系统在解析入口抛出可识别的解析错误，且不产生部分行为树结果

#### Scenario: 同一输入确定性输出
- **WHEN** 对同一份文档以相同解析参数调用两次
- **THEN** 两次返回的行为树对象结构完全一致（确定性）

### Requirement: 块引用解析

系统 SHALL 解析行为树文档中的块引用（`ref:`）。**一文档一树下，引用目标为另一文档的整棵树**：`ref: 文档名`，运行时加载被引文档并从其 Root 节点执行。系统 SHALL 通过解析入口传入的引用解析器（`RefResolver`）按文档名加载被引文档，且 MUST 在目标文档不存在时判定校验失败。引用 MUST 保留为调用节点 `RefNode`（不内联展开）。

#### Scenario: 引用当前文档命名块
- **WHEN** 文档中出现 `ref: 文档B`（一文档一树，引用另一文档整棵树）
- **THEN** 系统按文档名经引用解析器加载文档B，生成 `RefNode`（目标 `文档B`），运行时从文档B的 Root 执行

#### Scenario: 跨文档引用命名块
- **WHEN** 文档中出现 `ref: 文档B`（一文档一树下即跨文档引用，无块名第二段）
- **THEN** 系统按文档名加载文档B整棵树，生成 `RefNode`（目标 `文档B`）

#### Scenario: 引用不存在的块
- **WHEN** `ref:` 指向不存在的文档
- **THEN** 系统清晰度校验判定引用不存在，校验报告包含指明缺失文档的可读错误

#### Scenario: ref 参数对齐
- **WHEN** `ref:` 带 `args`/`returns`，且与被引文档的 `inputs`/`outputs` 声明数量/顺序/类型不匹配
- **THEN** 系统清晰度校验判定参数不匹配，报告指明问题

#### Scenario: 跨文档引用环校验
- **WHEN** 文档A引用文档B、B（直接或间接）又引用A
- **THEN** 系统清晰度校验判定跨文档循环引用，报告指明环路径

#### Scenario: args 字面量传入
- **WHEN** `args` 元素不是本树已存在的变量名
- **THEN** 系统将其作为字面量（str/int/float/bool）传入，并校验与对应 `inputs` 声明的类型匹配

## REMOVED Requirements

### Requirement: schema 绑定声明提取（多块形式）
**Reason**: 一文档一树取代多块模型，`blocks`（多块声明表）与 `this/块名` 同文档引用不再存在；块声明上移为文档级 `inputs`/`outputs`。
**Migration**: 文档级声明替代块声明；`ref: this/块` 改为 `ref: 文档名`（引用另一文档整棵树）；`blocks_tree` 语义变为"文档名→树"。

### Requirement: 配置参数覆盖声明识别（块级）
**Reason**: 配置参数从块级上移为文档级（`tree` 下的 `timeout`/`retry`/`browser` 保留名），块概念移除。
**Migration**: 配置参数写在文档顶层（`tree` 下），语义不变（名称固定、含义固定、向上查找与全局默认）。