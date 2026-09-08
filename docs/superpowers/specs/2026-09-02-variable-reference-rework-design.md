# 变量引用语法重构与 blackboard 接口设计

> 日期：2026-09-02
> 状态：设计稿（待用户审阅）
> 范围：M2 解析器 / M3 schema / M5 引擎函数 / M6 叶子执行 / M8 报告 / M9b 后端 / M9a 前端

## 背景与动机

当前变量读写符号（`=> $this/xxx` 写入、`{{$this/xxx}}` 读取）存在两个问题：

1. **边界不清**：`=> $this/param` 无前后包裹，与自然语言描述混在一起难以区分；`$` 前缀符号需记忆。
2. **读取无运行时实现**：`{{$this/xxx}}` 在 M2 只做作用域校验，运行时**没有任何替换逻辑**——LLM 看不到 blackboard 真实值，只能猜。变量引用本应是确定性动作，不应依赖 LLM。

## 目标

1. 统一的**前后有界**引用符号，明确与自然语言区分。
2. **读取确定性替换**：`{{get:...}}` 由程序在叶子执行前从 blackboard 取真实值替换，LLM 无感知。
3. **写入目标确定性声明**：`{{set:...}}` 声明可写变量集，程序校验，LLM 决定何时调用存储。
4. 提供 blackboard 查询接口，前端报告页实时展示当前变量。

## 设计

### 1. 符号体系（替代 `=>` / `{{$...}}`）

| 语法 | 语义 | 参与方 |
|---|---|---|
| `{{get:this/param}}` | 读取变量，叶子执行前**程序确定性替换**为真实值 | 程序 |
| `{{set:this/param}}` | 声明"此动作结果可存入该变量" | LLM 决定调用存储，程序校验目标 |
| `this/param`、`this/子块/param` | 变量路径（`this`=当前 schema 关键字，无 `$`） | 程序解析 |

**路径规则**（§5.3 层级不变）：
- `this/param`：当前块 schema 的变量
- `this/直接子块/param`：直接子块 schema（传参/取返回值，逐层，§5.3.2）

### 2. 读取机制（get）

```
M2 解析: 识别 {{get:this/param}} → 作用域校验（沿用现有 _READ_TMPL 改造）
  → 保留替换标记（含目标路径）
   │
叶子执行前 (M6 execute_leaf, build_user_message 之前):
  引擎从 blackboard (SchemaSpace.read) 查值
  → {{get:this/param}} 替换为真实值 (如 "ORD-001")
  → 注入 LLM 用户消息
  变量未定义 → 程序直接报错（该叶子执行失败，等价节点 FAILURE，不注入 LLM）
```

**确定性**：LLM 看到的永远是真实值，不需要调函数读变量。**读取失败是程序错误**（叶子直接 FAILURE，不让 LLM 猜测），失败场景包括：

- **变量未定义**：引用的变量尚未写入 blackboard
- **作用域违规**：引用的变量不在当前节点可见范围（违反 §5.3.2 可见规则——只能读自身帧与直接子帧；祖先/兄弟/孙子帧不可见）

两种失败都在 M6 叶子执行前由程序判定并返回 FAILURE（对应错误码区分「未定义」与「越权」，供报告定位）。

### 3. 写入机制（set）

```
M2 解析: 提取描述中全部 {{set:this/param}} → 作用域校验
  → 记录为该叶子"可写变量集" (set_targets)
   │
叶子执行 (M6): 把可写变量集注入提示词上下文（LLM 知道有哪些变量可写）
  │
LLM 决策: 决定调用 extract（或 open），传目标路径
  程序校验: extract 的 target 必须在"可写变量集"内，否则拒绝（未声明路径不能写）
```

**分工**：
- **程序**：确定"可写哪些变量"（声明集）
- **LLM**：决定"何时提取几个值、分别存哪"（仍需要，因一个 action 可能多动作/多变量）

### 4. blackboard 查询接口

```
M3: SchemaSpace.snapshot_variables(frame) → list[{path, type, value}]
    （导出当前帧 storage/declared，含子帧）
M8: ExecState 增加 variables: list[{path, type, value}]
M9b: GET /api/runs/{id}/state 响应含 variables
前端: 报告页"变量黑板"面板（usePolling 轮询更新）
```

## 涉及模块改动

| 模块 | 改动 |
|---|---|
| M2 parser | 新正则 `_GET_TMPL`/`_SET_TMPL` 识别 `{{get:...}}`/`{{set:...}}`；作用域校验；`ActionNode` 记录 `set_targets` |
| M3 schema | 新增 `snapshot_variables(frame)`；`resolve_target` 适配 `this/` 路径（去 `$`） |
| M5 engine | `extract` 增加"target 必须在声明集"校验（经 M6 传递） |
| M6 leaf | 叶子执行前 get 替换；set_targets 注入提示词；extract 调用传递校验上下文 |
| M6 prompts | 说明 `{{get:}}`（程序已替换，无需处理）与 `{{set:}}`（可写变量集）语义 |
| M8 reporting | `ExecState.variables` 字段 |
| M9b server | state 响应带 variables |
| M9a frontend | 报告页变量黑板面板 |

## 范围边界（本次实现）

- **本次范围**：叶子（Action/Condition）描述内的变量读写——`{{get:this/...}}`（读取替换）与 `{{set:this/...}}`（写入声明）。
- **不在本次范围**：ref 块引用传参（`ref:` 的 `写入:` 绑定键值）保持现状 `$this/` 语法，后续专门讨论。
- M3 内部保留 `$this` 兼容（解析层 `_is_self` 同时接受 `this`/`$this`），但用户文档与新代码用 `this/`。

## 兼容与迁移

- 旧 `=> $this/xxx` 与 `{{$this/xxx}}` 语法**不再保留**（叶子层），统一迁移到新语法 `{{get:...}}`/`{{set:...}}`。
- ref 块绑定 `写入:` 路径暂保留 `$this/`，等后续块绑定设计定案后统一。
- M2 解析器、M6 提示词、行为树文档示例更新为新语法。
- 契约 §5.3 文档改写为新语法（叶子层）。

## 测试

- M2：新语法解析（`{{get:}}`/`{{set:}}`）、作用域校验、set_targets 提取
- M6：get 替换成功、**get 未定义变量 → 叶子直接 FAILURE**、**get 作用域违规（祖先/兄弟/孙子帧）→ 叶子直接 FAILURE**、set 注入提示词、extract target 校验
- M3：snapshot_variables
- 端到端：行为树提取→set 存变量→后续 get 读取真实值；前端报告页变量黑板展示
