# 统一槽位模型设计（一文档一树 · v2）

日期：2026-09-11
状态：已获用户批准，进入实现

## 背景

原一文档一树 DSL 中，仅 Root/Sequence 使用 `slots` 引用子节点，IfThenElse/Retry/Branch 等仍保留"目标字符串字段"（then/else/body）或"分支行列表"（branches）的旧多块 DSL 残迹。这与用户确立的前端设计法则（**节点连线一律经槽位机制**）冲突。

本次设计确立**统一槽位模型**：行为树节点只保留核心语义，节点间的一切"动作/后续步骤"关联一律通过**槽位引用子树根节点**表达；条件（Condition）是概念性节点，内嵌为各节点的自有字段，不独立成用户可见类型。

## 核心原则

1. **节点只保留核心含义**：Sequence=顺序、Branch=分流、Retry=重试……具体每一步是 Action 还是 Step 还是 Sequence，通过槽位挂载的子树根节点体现，节点自身不关心。
2. **动作一律走槽位**：凡"执行某操作/某步骤"，都是槽位字段引用一个子树根节点 id。
3. **条件归属节点自身**：`when`/`if`/`until`/`expect` 是节点自有字段（Condition 概念内嵌），不通过槽位。
4. **Action 是真正叶子**：表达"单个操作"，可被任意槽位挂载。
5. **存储按节点语义命名槽位字段**（直观），前端画布/执行器经统一"挂载点"抽象消费。

## 节点类型

| 节点 | 语义 | 槽位字段（值=子树根 id） | 自有字段 |
|---|---|---|---|
| **Action** | 真正的叶子：执行一个操作 | — | `description`（操作描述） |
| **Step** | Action + Condition 复合：操作 + 验证 | `action: id` | `expect`（验证条件） |
| **Root** | 树的根，执行其主体 | `body: id` | — |
| **Sequence** | 顺序执行 | `actions: [id, id]` | — |
| **IfThenElse** | 判 `if` → 分流 | `then: id`、`else: id` | `if`（判断条件） |
| **Branch** | 先执行 action 子树，再按条件分流 | `action: id`、`branches: [{when, action: id} \| {otherwise, action: id}]` | — |
| **Retry** | 反复执行 body 直到成功 | `body: id` | `max` |
| **LoopUntil** | 每轮先判条件，不满足才执行 | `action: id` | `until`（终止条件）、`max` |
| **ref** | 跨文档引用（叶子） | — | `target`、`args`、`returns` |

Condition 概念内嵌字段：`Step.expect`、`IfThenElse.if`、`Branch.branches[].when`、`LoopUntil.until`。

## DSL 示例

```
tree: 订单流程
inputs: {起始订单: str}
outputs: [处理结果]
nodes:
  n1: {type: Root, name: 根, body: n2}
  n2: {type: Sequence, name: 主流程, actions: [n3, n4]}
  n3:
    type: Step
    name: 登录
    action: n5
    expect: 出现"工作台"
  n5: {type: Action, name: 点登录, description: 点击"登录"按钮}
  n4:
    type: Branch
    name: 处理审批
    action: n6
    branches:
      - when: 出现"已批准"
        action: n7
      - otherwise:
        action: n8
  n6: {type: Action, name: 查状态, description: 查询审批状态}
  n7: {type: Step, name: 导出, action: n9, expect: 导出成功}
  n9: {type: Action, name: 导出, description: 导出报表}
  n8: {type: Action, name: 重试, description: 稍后重试}
root: n1
```

## 执行语义（行为树遍历）

- **Root**：执行 `body` 子树。
- **Sequence**：按 `actions` 顺序执行各子树；任一失败 → 整体失败。
- **Step**：执行 `action` 子树（操作），随后验证 `expect` 条件。
- **IfThenElse**：不先操作，直接判 `if`；成立执行 `then` 子树，否则执行 `else` 子树。
- **Branch**：先执行 `action` 子树；随后按 `branches` 顺序检查 `when`，第一个命中者执行其 `action` 子树；无命中走 `otherwise` 分支的 `action` 子树（若有）。
- **Retry**：每轮执行 `body` 子树，成功即整体成功、失败重试，达 `max` 仍失败 → 整体失败（安全闸）。
- **LoopUntil**：每轮先判 `until`，满足即整体成功；不满足执行 `action` 子树后进入下一轮；达 `max` 仍不满足 → 整体失败。
- **Action**：叶子，执行 `description` 描述的单个操作（LLM/引擎）。
- **ref**：经 resolver 按文档名加载被引文档，从其 Root 执行；args（列表，按序对应被引树 inputs）注入、returns（字典，本树接收名→类型，按序对应 outputs）回收。

## 统一槽位抽象（前端画布 + 执行器共用）

每个容器节点类型声明「挂载点」：`slotFields(node) → [{label, field, childId}]`。

| 节点 | 挂载点 |
|---|---|
| Root | `body`（1 个，标签「主体」） |
| Sequence | `actions[i]`（N 个，标签「动作 i」） |
| Step | `action`（1 个，标签「操作」） |
| IfThenElse | `then`、`else`（2 个，标签「成立/否则」） |
| Branch | `action`（标签「前置操作」）+ `branches[i].action`（每分支 1 个，标签「分支 i」） |
| Retry | `body`（1 个，标签「重试体」） |
| LoopUntil | `action`（1 个，标签「循环体」） |
| Action / ref | 无（叶子） |

- **布局/连线**：所有挂载点连线到其子树根节点；画布根在上、向下生长、兄弟水平均布；主树 + 游离区。
- **游离判定**：nodes 池中未被任何挂载点引用的节点为游离根（含 ref/叶子单节点）。
- **删除/修改语义**（不变，AGENTS 前端设计法则）：
  - 删槽位 = 解引用：清空该挂载点引用，子树回游离区独立成树。
  - 删单节点 = 该节点各挂载点子树各自成为独立游离树。
  - 删子树 = 连带删除全部后代。
  - 改槽位 = 旧子树回游离区、新子树入该挂载点。
  - 根节点（Root）不可删除/替换；文档恰一个 Root。
- **前端便利**：创建 Step 自动附带一个 Action 子节点挂入其 `action` 槽位。

## 校验规则（前端即时 + 后端权威）

- 单根：恰一个 `type: Root` 且 `root` 引用指向它。
- 必填：Action `description`；Step `action`+`expect`；IfThenElse `if`+`then`+`else`；Branch `action` + 至少一个分支（when 非空或 otherwise）；Retry `body`+`max`；LoopUntil `until`+`action`+`max`；ref `target`。
- 槽位引用存在、无重复引用（纯树）；主树与各游离树无环；跨文档引用环检测。
- ref 参数对齐：args 数量/顺序/类型、returns 数量/接收名不重名/类型、字面量。

## 影响面（全部适配）

- **M2 parser**：`onedoc.py`/`document.py`/`models.py` 重写节点构成（槽位字段按类型解析），`ParseResult`/IRNode/Node 模型扩展。
- **M5 展开**：`expand.py` 复合节点展开适配槽位子树（Step/Branch/IfThenElse/Retry/LoopUntil 用子树而非内联字段）。
- **M7 执行器**：`traverser.py` 遍历适配（Branch 分流执行子树、Step 执行 action 子树 + 验证、Action 叶子）。
- **前端**：`treeModel.ts`/`layout.ts`/`validation.ts`/画布 UI 适配统一挂载点。
- **文档**：contract.md、M2/M5/M6/M7/M9a/M9b specs、openspec change specs。
- **测试**：后端 parser/expand/executor 全量重写相关用例；前端 model/layout/validation/UI + E2E。