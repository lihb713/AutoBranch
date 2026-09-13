## MODIFIED Requirements

### Requirement: 引擎运行入口

系统 SHALL 提供 `engine.run(tree, doc_decl, config, resolver)` 入口，接收内部行为树、文档级接口声明与运行配置，完成会话初始化后对行为树执行一次确定性遍历。运行结束后系统 SHALL 返回运行结果，包含最终状态（`success` / `failure`）、失败原因（失败时非空）、执行报告与回溯报告。当行为树清晰度校验失败时，系统 SHALL 返回可供修正的错误信息，且不启动任何遍历。

#### Scenario: 行为树整体执行成功
- **WHEN** 调用方以合法行为树、文档声明、配置与引用解析器调用 `engine.run`
- **THEN** 系统返回状态为 `success` 的运行结果，失败原因为空，且附带完整的执行报告与回溯报告

#### Scenario: 叶子失败导致整体失败并携带原因
- **WHEN** 行为树中某叶子节点执行失败并沿树传播到根
- **THEN** 系统返回状态为 `failure` 的运行结果，失败原因指向该叶子节点，并附带完整的执行报告与回溯报告

#### Scenario: 校验失败不启动遍历
- **WHEN** 调用方传入无法通过清晰度校验的行为树（如引用文档不存在、节点配置缺失、树有环）
- **THEN** 系统返回校验失败的错误信息，不启动任何节点遍历，也不产出执行报告

### Requirement: 复合节点执行语义（统一槽位）

系统 SHALL 按统一槽位模型遍历复合节点：每个容器节点的动作经槽位字段递归执行其子树根节点。语义如下：

- **Root**：执行 `body` 子树。
- **Sequence**：按 `actions` 顺序执行各子树；任一失败 → 整体失败。
- **Step**：执行 `action` 子树（操作），随后验证 `expect` 条件。
- **IfThenElse**：不先操作，直接判 `if`；成立执行 `then` 子树，否则执行 `else` 子树。
- **Branch**：先执行 `action` 子树；随后按 `branches` 顺序检查 `when`，第一个命中者执行其 `action` 子树；无命中走 `otherwise` 分支的 `action` 子树（若有）。
- **Retry**：每轮执行 `body` 子树，成功即整体成功、失败重试；达 `max` 仍失败 → 整体失败。
- **LoopUntil**：每轮先判 `until`，满足即整体成功；不满足执行 `action` 子树后进入下一轮；达 `max` 仍不满足 → 整体失败。
- **Action**：叶子，执行 `description` 描述的单个操作。

#### Scenario: Sequence 顺序执行
- **WHEN** 遍历 Sequence 节点
- **THEN** 按 `actions` 槽位顺序递归执行各子树，任一子树失败即整体失败

#### Scenario: Branch 分流
- **WHEN** 遍历 Branch 节点
- **THEN** 先执行其 `action` 子树，再按 `branches` 顺序判 `when`，第一个命中者执行其 `action` 子树；无命中执行 `otherwise` 分支的 `action` 子树

#### Scenario: IfThenElse 分流
- **WHEN** 遍历 IfThenElse 节点
- **THEN** 直接判 `if` 条件，成立执行 `then` 子树、否则执行 `else` 子树，不先执行操作

#### Scenario: Step 执行操作子树并验证
- **WHEN** 遍历 Step 节点
- **THEN** 执行 `action` 槽位子树（操作），随后验证 `expect` 条件

#### Scenario: Retry / LoopUntil 循环
- **WHEN** 遍历 Retry 或 LoopUntil 节点
- **THEN** 分别按"反复执行 body 直到成功"与"每轮先判 until、不满足执行 action 子树"循环，达 `max` 安全闸失败

### Requirement: 引用节点动态调用（跨文档）

系统 SHALL 在遍历到引用节点（`RefNode`）时执行动态调用：经引用解析器按文档名加载被引文档的行为树，从其 Root 节点开始执行（建子帧、按 args 注入入参、回收 returns 到父帧、退出子帧）。被引文档不存在时该引用节点 SHALL 返回 FAILURE 并携带明确错误。

#### Scenario: 引用另一文档并执行
- **WHEN** 遍历到 `ref: 文档B` 且文档B存在
- **THEN** 系统加载文档B的树，从B的Root执行，其 output 按 returns 写回父帧，执行结果反映在整体遍历中

#### Scenario: 引用文档不存在
- **WHEN** 遍历到 `ref: 文档B` 且文档B不存在
- **THEN** 该引用节点返回 FAILURE，失败原因指明文档B不存在

#### Scenario: 多层引用逐层执行
- **WHEN** 文档A引用文档B、B又引用文档C
- **THEN** 系统逐层加载执行（A→B→C），各层帧独立，returns 逐层回收

#### Scenario: 跨文档引用环运行时防护
- **WHEN** 遍历中形成跨文档循环引用（A→B→A，即使校验漏过或运行时文档关系变化）
- **THEN** 系统以引用深度上限拦截（达到上限返回 FAILURE），不无限递归

### Requirement: 帧生命周期（一文档一树）

系统 SHALL 为每次引用调用创建独立 schema 帧：入参注入子帧、执行被引树、returns 回收写父帧、退出子帧。帧数据保留至整个行为树运行结束（供黑板上报各调用帧变量），执行期间激活帧控制访问权限。

#### Scenario: 引用调用建帧与回收
- **WHEN** 引用节点执行子帧
- **THEN** 子帧接收 args 注入的入参，执行后 output 按 returns 写父帧，子帧退出但数据保留至运行结束