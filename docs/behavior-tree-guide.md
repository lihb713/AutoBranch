# AutoBranch 行为树指南

> 面向第一次接触 AutoBranch 的读者。读完本文，你应能独立写出、理解并调试一棵行为树。
>
> 相关文档：
> - [插件开发指南](plugin-development-guide.md)
> - [内置插件介绍](builtin-plugins.md)
> - [完整用户手册](user-guide.md)

## 1. AutoBranch 在做什么

AutoBranch 用一棵**行为树**描述自动化流程：

- **流程骨架是确定的**：先做什么、后做什么、失败重试几次、循环多少次，都由你写的树决定；
- **叶子动作交给 LLM**：Action/Condition 这类叶子可以根据自然语言描述理解当前页面、选择插件函数；
- **确定性节点不经 LLM**：`FunctionCall`、`Define` 等节点直接执行，结果可预测；
- **结果写入黑板**：变量在树内传递，最终通过出参和报告展示。

一句话：**行为树负责“流程”，LLM 只在叶子节点内负责“具体怎么做”。**

### 1.1 为什么是“确定性骨架 + LLM 叶子”

如果整条流程都交给 LLM，会出现三个问题：

1. **不可复现**：同样的输入，LLM 可能选择不同步骤；
2. **难审计**：失败时很难判断是流程错了还是某一步理解错了；
3. **成本与延迟不可控**：连“先登录再下单”这种确定顺序也要消耗 LLM 轮次。

AutoBranch 的取舍是：

- 流程顺序、循环、重试、分支、入参出参全部写成树，**由程序确定性执行**；
- 只有真正需要理解页面/自然语言/环境的一小步，才交给 LLM；
- LLM 的结果必须落到明确变量或明确节点结果，便于报告、重试和复盘。

因此你会看到 `FunctionCall`、`Define` 这类“不给 LLM 决策权”的节点，也会看到 `Action` 这种“把决策权限制在一个叶子里”的节点。

## 2. 先认识几个概念

| 概念 | 说明 |
|---|---|
| Root | 整棵树的起点，只有一个 |
| Sequence | 顺序执行，全部成功才成功，遇到失败立即停止 |
| Step | 一次“操作 + 验证”：执行 action 槽位，再用 `expect` 判断 |
| Action | 真正交给 LLM 执行的叶子，用自然语言写操作目标 |
| IfThenElse | 条件成立走 `then`，否则走 `else` |
| Branch | 多分支，每个分支有 `when` 或 `otherwise` |
| Retry | 失败后重试，最多 `max` 次 |
| LoopUntil | 循环直到 `until` 成立或达到 `max` |
| ForEach | 遍历列表/字典，每一轮把当前项写入临时变量 |
| ref | 调用另一份行为树，像调用子程序 |
| FunctionCall | 直接调用插件函数，不经 LLM |
| Define | 确定性声明变量 |
| 黑板 | 当前执行帧中的变量空间 |
| 入参/出参 | 一棵树的输入变量与输出变量 |
| 报告 | 每个节点的执行结果、耗时、失败原因、函数调用等 |

### 2.1 成功与失败

每个节点最终返回 `SUCCESS` 或 `FAILURE`：

- Sequence：任一子节点失败，整体失败；全部成功才成功；
- IfThenElse：只执行命中的分支；
- Retry：失败后重试，超过次数仍失败则整体失败；
- LoopUntil：条件成立提前结束；达到 `max` 仍未成立则失败；
- Step：action 成功且 `expect` 成立才算成功。

## 3. 最小可运行示例

```yaml
tree: 打开主页
nodes:
  r:
    type: Root
    name: 根
    body: s1
  s1:
    type: Step
    name: 打开主页并确认
    action: a1
    expect: 页面出现“欢迎”
  a1:
    type: Action
    name: 打开主页
    description: 打开 https://example.com
root: r
```

执行过程：

1. `Root` 进入 `s1`；
2. `s1` 先执行 `a1`：LLM 读取“打开 https://example.com”，选择浏览器插件的 `open` 等能力；
3. 操作成功后，LLM 再判断 `expect`：“页面出现‘欢迎’”；
4. 两者都成功，`s1` 与整棵树成功。

## 4. 行为树文档结构

一份 YAML 文档对应一棵树：

```yaml
tree: 文档名
inputs:
  user: str
outputs:
  result: str
timeout: 300
retry: 1
browser:
  headless: true
nodes:
  # 节点对象池：id -> 节点
  r:
    type: Root
    name: 根
    body: s1
root: r
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `tree` | 是 | 文档名；保存时须与树名一致 |
| `inputs` | 否 | 入参声明：`{变量名: 类型}` |
| `outputs` | 否 | 出参声明：`{变量名: 类型}` |
| `config` 覆盖项 | 否 | `timeout` / `retry` / `browser` 等 |
| `nodes` | 是 | 节点对象池，键为节点 id |
| `root` | 是 | 指向唯一 `type: Root` 节点的 id |

### 4.1 节点 id 与槽位

节点 id 必须是 ASCII 标识符：

```text
[A-Za-z_][A-Za-z0-9_]*
```

槽位字段表示“这里挂一棵子树”，值是被挂节点的 id：

| 节点 | 槽位 |
|---|---|
| Root | `body` |
| Sequence | `actions`（列表） |
| Step | `action` |
| IfThenElse | `then` / `else` |
| Branch | `action` + `branches[]` |
| Retry | `body` |
| LoopUntil | `action` |
| ForEach | `body` |

同一个节点不能被两个槽位同时引用；这保证它始终是一棵**纯树**。

## 5. 节点参考

### 5.1 Sequence：顺序执行

```yaml
n2:
  type: Sequence
  name: 主流程
  actions: [n3, n4, n5]
```

### 5.2 Step：操作 + 验证

```yaml
n3:
  type: Step
  name: 登录
  action: n4
  expect: 出现“工作台”
n4:
  type: Action
  name: 执行登录
  description: 在用户名输入 admin，密码输入 secret，点击登录
```

`Step` 必须有 `action` 和 `expect`。`Action` 必须有自然语言 `description`；如果额外提供 `css_hint`，可作为定位提示，但并非必须。

### 5.3 Action：LLM 叶子

```yaml
n5:
  type: Action
  name: 提取订单金额
  description: 从订单详情页提取订单金额，保存为 NewParam.amount:float
```

Action 的特点是：

- 由 LLM 执行；
- 可以使用浏览器、SSH、文件、计算等插件能力；
- 不限于浏览器；
- 变量写入通过描述里的 `NewParam.变量:类型` 声明。

### 5.4 IfThenElse：条件分支

```yaml
n2:
  type: IfThenElse
  name: 是否已登录
  if: 页面出现“退出登录”
  then: n3
  else: n4
```

### 5.5 Branch：多分支

```yaml
n2:
  type: Branch
  name: 按状态分流
  action: n3
  branches:
    - when: 出现“审核通过”
      action: n4
    - when: 出现“审核拒绝”
      action: n5
    - otherwise: n6
```

`action` 是分流前的可选前置操作；`when` 按顺序判断；`otherwise` 表示兜底分支。

### 5.6 Retry：失败重试

```yaml
n2:
  type: Retry
  name: 最多重试 2 次
  max: 2
  body: n3
```

### 5.7 LoopUntil：循环直到条件成立

```yaml
n2:
  type: LoopUntil
  name: 翻页直到最后一页
  action: n3
  until: 出现“已经是最后一页”
  max: 20
```

必须提供 `max`，避免死循环。

### 5.8 ForEach：遍历

```yaml
n2:
  type: ForEach
  name: 遍历订单
  variables:
    order_id: Param.order_ids
  on_failure: continue
  body: n3
```

- `variables` 的值为列表，或能解析为列表的 `Param.x` / JSON 文本；
- 每一轮把当前项写入同名临时变量；
- 循环体内用 `Param.order_id` 读取；
- `on_failure`：
  - `continue`：跳过失败项继续；
  - `abort`：立即失败退出。

### 5.9 Define：声明变量

```yaml
n2:
  type: Define
  name: 初始化结果
  vars:
    result: {type: object, value: {}}
    count: {type: int, value: "0"}
    base_url: {type: str, value: "https://api.example.com"}
```

`Define` 是确定性节点，不经 LLM。`value` 可以是：

- 字面量；
- `Param.x`（复制另一个变量）；
- YAML dict/list（用于 `object` / `array`）。

### 5.10 ref：调用另一棵行为树

```yaml
n2:
  type: ref
  name: 登录子流程
  target: 登录流程
  args: [Param.username, Param.password]
  returns: {token: str}
```

详见第 7 节。

### 5.11 FunctionCall：确定性调用插件函数

```yaml
n2:
  type: FunctionCall
  name: 求和
  function: compute.add
  args: [Param.a, Param.b]
  returns: {total: float}
```

详见第 8 节。

### 5.12 如何选择节点：Action、FunctionCall、Define、ref

这是写行为树时最常遇到的四个选择。

| 你想做什么 | 推荐节点 | 原因 |
|---|---|---|
| 需要理解页面、文本、环境后决定操作 | `Action` | 只有这里需要 LLM 判断 |
| 调用已知插件函数、结果确定 | `FunctionCall` | 不经 LLM，快、稳定、可测试 |
| 初始化常量、空容器、循环累加器 | `Define` | 确定性创建变量，不消耗 LLM |
| 复用另一棵树的完整流程 | `ref` | 通过 inputs/outputs 形成清晰接口 |
| 遍历一个列表/字典 | `ForEach` | 数据驱动，自动管理当前项 |
| 条件成立就停 | `LoopUntil` | 条件驱动，必须写 `max` 防死循环 |

#### 为什么需要 `FunctionCall`，而不是所有插件都交给 LLM？

因为很多步骤根本不需要“理解”：

- 两数相加；
- JSON 解析；
- 拼接 URL；
- 读写文件；
- 用已知参数调用 HTTP 接口。

这些步骤交给 LLM 只会增加随机性、成本和延迟。`FunctionCall` 让它们成为普通程序调用，并且能在报告里精确看到参数和返回值。

#### 为什么需要 `Define`，而不是都用 `NewParam`？

`NewParam` 解决的是：**LLM 在 Action 中产出一个值，要写到哪个变量**。它天然依赖 LLM 执行。

`Define` 解决的是另一类问题：**流程开始前/循环前，确定性地准备变量**。

典型场景：

```yaml
# 初始化空字典，后面循环里累加
vars:
  summary: {type: object, value: {}}

# 初始化计数器
vars:
  count: {type: int, value: "0"}

# 固定配置
vars:
  base_url: {type: str, value: "https://api.example.com"}
```

如果这些也用 `NewParam` 让 LLM 去“写”，会产生三个问题：

- 明明不需要 LLM，却多了一次调用；
- LLM 可能写错初始值；
- 空 dict/list 很难通过自然语言稳定表达。

所以：**需要 LLM 产出值时用 `NewParam`；需要程序准备值时用 `Define`。**

#### 为什么需要 `ref`，而不是复制粘贴子树？

复制粘贴会带来：

- 修改登录流程时要改很多份；
- 入参/出参没有契约；
- 报告里看不出“这是子流程”。

`ref` 把另一棵树当成有接口的子程序：

- 入参 `inputs`；
- 出参 `outputs`；
- 可复用、可独立测试；
- 报告中有独立的子流程调用记录。

#### 为什么 `ForEach` 和 `LoopUntil` 要分开？

- `ForEach`：**已经有数据**，要对每个元素执行一次；
- `LoopUntil`：**没有固定数据**，靠条件判断何时停止（如翻页直到最后一页）。

两者的失败语义、终止条件、临时变量都不同，混在一起会让行为树难以理解。

## 6. 变量与黑板

变量是行为树在运行期传递数据的核心。

### 6.1 读取：`Param.x`

在 Action/Condition 描述、FunctionCall 参数、ref 参数中读取变量：

```text
打开 Param.base_url
```

```yaml
args: [Param.user, Param.password]
```

### 6.2 写入：`NewParam.x[:类型]`

在 **Action 的 description** 中声明写入目标：

```text
提取订单金额，保存为 NewParam.amount:float
```

`NewParam` 只负责声明“这个 LLM 叶子可以写哪个变量”。实际写值由插件函数的 `save_to`/`target` 或 LLM 提取动作完成。

**为什么要有 `NewParam` 声明，而不是让 LLM 随便写变量？**

- 限制 LLM 只能写你允许的变量，避免污染黑板；
- 让保存/执行前校验能发现拼写错误；
- 让报告能明确显示“这个值写到了哪个变量”；
- 让提示词可以只注入相关变量，降低上下文噪声。

**什么时候不该用 `NewParam`？**

- 变量是固定常量/空容器 → 用 `Define`；
- 变量来自确定性函数 → 用 `FunctionCall` 的 `returns`；
- 变量来自另一棵树的输出 → 用 `ref` 的 `returns`。

### 6.2.1 变量来源速查

| 变量来源 | 使用方式 | 是否经 LLM |
|---|---|---|
| 树入参 | `inputs` + 执行时填参 | 否 |
| 固定值/空容器 | `Define` | 否 |
| 确定性函数结果 | `FunctionCall.returns` | 否 |
| 子流程输出 | `ref.returns` | 否 |
| LLM 从页面/文本提取的值 | Action 中 `NewParam.x` + `save_to`/`target` | 是 |
| LLM 直接生成的值（总结、分类等） | Action 中 `NewParam.x` + `vars.set` | 是 |
| 循环当前项 | `ForEach.variables` | 否 |

### 6.3 声明：Define

确定性创建变量，适合初始化常量、空容器、循环累加器：

```yaml
vars:
  total: {type: float, value: "0"}
  result: {type: object, value: {}}
  items: {type: array, value: []}
```

### 6.4 作用域

- 每份文档有独立执行帧；
- 默认只能读写自己的帧；
- `ref` 子文档通过 `args` / `returns` 与调用方交换数据；
- `ForEach` 每轮创建子帧，但子帧可以向上读取当前行为树帧。

### 6.5 类型系统

核心类型：

| token | 含义 | 文本输入 |
|---|---|---|
| `str` | 字符串 | 任意文本 |
| `int` | 整数 | `"42"` |
| `float` | 浮点数 | `"3.14"` |
| `bool` | 布尔 | `true/false/1/0/yes/no` |
| `array` | Python list | JSON 数组，如 `[1,2,3]` |
| `object` | Python dict | JSON 对象，如 `{"host":"x"}` |
| `generics` | 不确定类型 | 原样接收，不转换 |
| `page_ref` | 核心自定义页签类型 | 不可文本构造 |

插件还可以注册自己的自定义类型，例如：

| token | 来源 | 含义 |
|---|---|---|
| `page_object` | browser | 浏览器页面对象 |
| `ssh_session` | ssh | SSH 会话对象 |

自定义类型不可由文本构造，只能来自插件返回值或 ref 传递。

### 6.6 类型如何转换

- **用户填写入参**：array/object 的 JSON 文本会转成 list/dict；
- **插件返回 list/dict**：保存到黑板时保持 list/dict，不再转字符串；
- **函数参数**：参数声明为 array/object 时，字面量文本按 JSON 构造；
- **自定义类型**：保持对象本身，不做文本化。

### 6.7 变量进入 LLM 提示词时的规则

- 标量、以及**全部由基本值组成的 array/object**：描述中的 `Param.x` 会替换成实际值；
- `generics`、`page_ref`、插件自定义类型：保留 `Param.x`，由变量表提供对象信息；
- **包含自定义值的 list/dict**：同样保留 `Param.x`，避免把 PageRef/SSH 会话等对象硬转成字符串。

### 6.8 变量从哪来

变量来源包括：

1. 树入参 `inputs`；
2. `Define` 声明；
3. `NewParam.x` + 插件/LLM 写入；
4. `FunctionCall` / `ref` 的 `returns` 接收名；
5. `ForEach` 的每轮临时变量。

### 6.9 命名规则

- 变量名、节点 id、returns 接收名都必须是 ASCII 标识符；
- 不支持中文、点号、斜杠；
- 反引号包裹的内容按纯文本处理。

## 7. 跨文档引用 `ref`

`ref` 让一棵树调用另一棵已发布的行为树。

### 7.1 被调用方

```yaml
tree: 登录流程
inputs:
  user: str
  pwd: str
outputs:
  token: str
nodes:
  r:
    type: Root
    body: s1
  s1:
    type: Step
    name: 登录
    action: a1
    expect: 出现“工作台”
  a1:
    type: Action
    name: 执行登录
    description: 使用 Param.user / Param.pwd 登录，保存 token 到 NewParam.token:str
root: r
```

### 7.2 调用方

```yaml
n2:
  type: ref
  name: 调用登录流程
  target: 登录流程
  args: [Param.username, Param.password]
  returns: {token: str}
```

规则：

- 目标文档必须存在且为正式版；
- `args` 按目标 `inputs` 顺序传值；
- `returns` 的键是本树接收变量名，数量与目标 `outputs` 对齐；
- 不允许跨文档循环引用；
- 子文档只通过 args/returns 交换变量，不直接读调用方局部变量。

## 8. FunctionCall：确定性调用

### 8.1 基本写法

```yaml
n2:
  type: FunctionCall
  name: 求和
  function: compute.add
  args: [Param.a, Param.b]
  returns: {total: float}
```

### 8.2 args 与 kwargs

- `args` 按函数参数顺序传位置参数；
- `kwargs` 按参数名传命名参数；
- 必填参数可由 args 或 kwargs 提供；
- `kwargs` 适合跳过中间可选参数：

```yaml
n2:
  type: FunctionCall
  function: compute.compare
  args: [Param.a, Param.b]
  kwargs:
    op: gt
  returns: {ok: bool}
```

### 8.3 array/object 字面量

```yaml
args: ["[1,2,3]", ","]
```

如果函数参数类型是 `array`，字符串 `"[1,2,3]"` 会在执行时构造成 list；`object` 同理。

更推荐直接使用变量：

```yaml
args: [Param.items, ","]
```

### 8.4 返回值

```yaml
returns: {total: float}
```

接收名由你填写；类型来自函数声明，用户不可改。未填写接收名时系统会生成默认名。

### 8.5 自定义类型返回值

```yaml
n2:
  type: FunctionCall
  name: 建 SSH 会话
  function: ssh.create_session
  args: [Param.host, Param.port]
  returns: {session: ssh_session}
n3:
  type: FunctionCall
  name: 执行命令
  function: ssh.ssh_exec
  args: [Param.session, "ls -la"]
  returns: {stdout: str}
```

`ssh_session` 是插件注册的自定义类型，不是 `generics`。

### 8.6 行为树里如何标注自定义类型

树级接口直接写真实类型：

```yaml
tree: 远程检查
inputs:
  session: ssh_session
  command: str
outputs:
  stdout: str
nodes:
  r:
    type: Root
    body: n2
  n2:
    type: FunctionCall
    name: 执行远程命令
    function: ssh.ssh_exec
    args: [Param.session, Param.command]
    returns: {stdout: str}
root: r
```

说明：

- `inputs.session` 标注为 `ssh_session`，不是 `str`；
- `FunctionCall.args` 不需要重复写类型，参数类型由函数声明提供；
- `ssh_session` 不可由文本构造，因此这棵树通常作为 `ref` 子流程，由调用方通过 `session` 参数传入；
- 前端会显示 `ssh_session`，执行时会校验实际值是否为 `SSHConnection`。

## 9. 执行与报告

### 9.1 触发执行

在前端行为树列表点「执行」，或调用：

```http
POST /api/runs
Content-Type: application/json

{"tree_id": 12, "inputs": {"a": 2, "b": 3}}
```

也支持 `POST /api/trees/{id}/run`。

### 9.2 为什么执行要保存快照

执行与重试都基于**触发时刻的行为树快照**，而不是实时读取当前树。这样做的原因：

- 执行期间修改树不会改变正在跑/即将重试的流程；
- 失败后重试能复现当时的树内容；
- 历史记录可回看，即使树后来被修改或删除。

### 9.3 执行状态

```http
GET /api/runs/{id}/state
```

返回进度、当前节点、已完成节点、`status`、失败原因、变量黑板等。

### 9.4 报告

```http
GET /api/runs/{id}/report
GET /api/runs/{id}/trace
```

- 执行中：JSON 状态；
- 结束后：`text/markdown` 报告。

报告包含：

- 每个节点成功/失败；
- 耗时；
- 失败原因；
- 函数调用参数与返回值；
- 浏览器截图（有页面操作时）；
- LLM 决策过程（回溯报告）。

### 9.5 前端页面

- `/runs`：执行列表；
- `/runs/{id}`：执行详情、输入输出、快照、报告；
- 支持重试和删除。

## 10. 常见校验错误

| 错误 | 常见原因 |
|---|---|
| `missing_slot` | 必填槽位没挂子节点 |
| `missing_field` | Action 缺 description、Step 缺 expect 等 |
| `duplicate_reference` | 同一节点被多个槽位引用 |
| `cycle` / `cross_doc_cycle` | 树内或跨文档引用成环 |
| `unknown_function` | FunctionCall 函数名不存在 |
| `args_mismatch` | FunctionCall/ref 参数数量或必填参数不匹配 |
| `get_undeclared` | 读取了未声明变量 |
| `syntax.invalid_type` | NewParam 使用了未注册类型 |
| `locatable.not_locatable` | Action 既没有描述也没有 CSS 提示 |

## 11. 完整示例

### 11.1 计算并输出

```yaml
tree: 计算和
inputs:
  a: int
  b: int
outputs:
  total: float
nodes:
  r:
    type: Root
    name: 根
    body: n2
  n2:
    type: FunctionCall
    name: 求和
    function: compute.add
    args: [Param.a, Param.b]
    returns: {total: float}
root: r
```

### 11.2 数组/对象入参

```yaml
tree: 拼接 URL
inputs:
  items: array
  payload: object
outputs:
  joined: str
  url: str
nodes:
  r:
    type: Root
    body: n2
  n2:
    type: Sequence
    name: 串联
    actions: [n3, n4]
  n3:
    type: FunctionCall
    function: transform.join
    args: [Param.items, ","]
    returns: {joined: str}
  n4:
    type: FunctionCall
    function: transform.format
    args: ["http://{host}:{port}/api", Param.payload]
    returns: {url: str}
root: r
```

执行时填写：

```json
{
  "items": "[1,2,3]",
  "payload": "{\"host\":\"example.test\",\"port\":8080}"
}
```

### 11.3 ForEach 遍历

```yaml
tree: 遍历订单
inputs:
  order_ids: array
nodes:
  r:
    type: Root
    body: n2
  n2:
    type: ForEach
    name: 遍历订单
    variables:
      order_id: Param.order_ids
    on_failure: continue
    body: n3
  n3:
    type: Action
    name: 处理订单
    description: 打开订单 Param.order_id 并检查状态
root: r
```

每一轮 `order_id` 是当前项；`ForEach` 子帧可以读取外层变量，循环结束自动清理。

### 11.4 ref 组合

```yaml
tree: 下单流程
inputs:
  username: str
  password: str
nodes:
  r:
    type: Root
    body: n2
  n2:
    type: Sequence
    actions: [n3, n4]
  n3:
    type: ref
    name: 登录
    target: 登录流程
    args: [Param.username, Param.password]
    returns: {token: str}
  n4:
    type: FunctionCall
    name: 创建订单
    function: http.request
    args: ["POST", "https://api.example.com/orders"]
    kwargs:
      headers: {"Authorization": "Bearer Param.token"}
      json: {"sku": "A-1", "qty": 1}
    returns: {status: int, body: str}
root: r
```

## 12. 下一步

- 想开发插件：阅读 [插件开发指南](plugin-development-guide.md)
- 想查内置函数：阅读 [内置插件介绍](builtin-plugins.md)
- 想安装、配置、部署：阅读 [完整用户手册](user-guide.md)
