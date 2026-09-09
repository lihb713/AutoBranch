# WebOps —— 自然语言驱动的 Web 自动化工具

> 本文件是 WebOps 的产品介绍与文档语法契约初稿（v1.9）。
> 它是后续一切功能实现的地基：**先定义清楚产品的使用方式，再谈页面理解与实现细节**。

---

## 1. 产品定位

WebOps 是一个基于自然语言的 Web 自动化工具。用户编写一份**行为树文档**（结构化书写流程，叶子内容用自然语言描述"要在网页上做什么"），WebOps 借助大语言模型（LLM）理解页面、执行节点、并输出操作日志与页面截图供回溯。

一句话概括：**你写流程，WebOps 替你跑网页。**

### 1.1 核心价值

- **文档驱动**：流程即文档，可读、可复用、可审计、可版本管理
- **自然语言**：用户不必懂 CSS / HTML / XPath，用日常语言描述"做什么"
- **可回溯**：每一步自动记录操作日志 + 页面截图，事后可核对
- **可对接任意模型**：用户配置自己的 LLM 接口（OpenAI 兼容的 base_url + api_key）

### 1.2 非目标（第一版）

- 不做视觉模型驱动（成本高、模型不普及）——采用非视觉的 DOM 观察方案
- 不做运行时的用户交互——批处理模式，遇意外即终止并出报告
- 不接入 Anthropic / Gemini 等非 OpenAI 兼容厂商（后续按需适配）
- 不做无限智能代理——**流程节点间的流转是确定的，LLM 只在单节点内行使有限的执行权**

---

## 2. 设计哲学（最高原则）

WebOps 的一切设计围绕一条最高原则：

> **流程节点之间的流转过程是确定的，不允许 LLM 自由发挥。**
> **每个叶子节点由 LLM 驱动，负责页面理解、动作执行与结果判断。**

这一定义拆分出三层职责，彼此正交：

```
┌────────────────────────────────────────────┐
│  ① 控制流层（确定性）                          │
│     步骤顺序 / 分支 / 循环 / 流转             │
│     完全由行为树结构决定，LLM 无权决定"下一步"  │
├────────────────────────────────────────────┤
│  ② 信息流层（确定性）                          │
│     变量定义 / 提取 / 引用 / 断言             │
│     跨块信息传递，规则引擎保证可校验           │
├────────────────────────────────────────────┤
│  ③ 单节点执行层（LLM 有界代理）                 │
│     观察理解页面 / 定位目标 / 执行动作 / 验证     │
│     LLM 只在此层内行使权力，范围限于"当前节点"     │
└────────────────────────────────────────────┘
```

### 2.1 双形式定位

任何对页面元素的描述，都支持两种形式并存：

- **自然语言**（用户友好）：如"点击登录按钮"
- **CSS / 选择器提示**（程序友好）：如 `CSS: button[type=submit]`

```
操作: 点击 "登录" 按钮
  CSS: button[type=submit]     ← 可选提示，命中优先
```

自然语言负责表达"意图"，CSS 负责提供"精度"。用户按自己的能力书写，能写多少写多少，缺的部分由 LLM 理解补足。

### 2.2 失败即止（无逃生通道）

这是与"智能代理"方案的关键区别。**执行中遇到任何意外**（弹窗遮挡、断言失败、定位失败、超时），WebOps **不会让 LLM 自由接管绕路**，而是：

1. 记录完整日志 + 截图
2. 终止当前流程
3. 提示用户"此步骤需要补充/修正文档"

用户据此完善行为树文档后重新运行。**换来的是：同一份文档，任何时刻运行的结果、日志、截图都是可比的** —— 这对审计、报表、批量处理场景至关重要。

---

## 3. 整体工作流

WebOps 分两个阶段运行：

```
┌─────── 阶段一: 书写行为树文档（用户在场）────────────┐
│  ┌────────────┐   ┌──────────────┐   ┌──────────┐  │
│  │ 用户直接书写  │──▶│ 行为树文档(结构化)│──▶│ 清晰度校验 │  │
│  │ 行为树文档   │   │   (yaml/dict) │   └────┬─────┘  │
│  └────────────┘   └──────────────┘      不通过│        │
│                                              ▼        │
│                                 返回用户修正文档 ──▶ 循环  │
│                                              │        │
│                                         通过(用户确认)  │
└──────────────────────────────────────────────┬─────────┘
                                               ▼
┌─────── 阶段二: 批处理执行（无用户）─────────────────────┐
│  程序解析行为树 → 遍历执行 → 日志 + 截图 + 报告          │
└──────────────────────────────────────────────────────┘
```

### 阶段一：书写行为树文档

- **用户直接书写行为树文档**（yaml/dict 格式，见 §4/§5.7），结构由用户确定，LLM 只填充叶子内容（操作/判断的自然语言描述）
- **清晰度校验**：程序解析行为树文档并校验（结构合法、引用存在、变量契约一致、循环有界），不通过则返回用户修正
- 反复迭代，直到行为树文档清晰、可执行，用户确认后才进入执行

### 阶段二：批处理执行（Run）

- 程序**解析行为树文档**为内部行为树对象
- 确定性编排器**遍历行为树**，组合节点纯程序流转，叶子节点（Action/Condition）激活 LLM 有界代理：理解页面 → 定位 → 执行/判断
- 全程记录节点执行情况 + 截图（§5.8.3 报告机制）
- 遇意外即终止，输出执行报告 + 回溯报告

---

## 4. 行为树文档格式（契约核心）

> **用户直接书写行为树文档**（yaml/dict），LLM 只填充叶子内容。结构由用户完全控制，这是确定性的来源。

### 4.1 文档结构总览

**文档顶层有两种合法形式**（解析器均支持）：

```
形式A（block 定义）:
行为树文档
├── block 定义（命名块集合, 可复用/可共享）
│     ├── 块名: <本块的 inputs/outputs 声明 + 行为树>
│     ├── 块名: ...
│     └── ...
└── 根流程（主入口, 组织块引用）
      └── 行为树 (基础节点 + 复合节点)

形式B（裸树）:
行为树文档 = 单个 dict, 整个即根块的行为树（根块名 = 文档名）
```

**一个行为树文档本身就是一个命名块**（块名 = 文档名），因此：

```
block 登录:                ← 根块 = 文档名, 整个文档就是"登录"这个块
  inputs: ...
  outputs: ...
  Sequence: ...
```

**顶层键语义（形式A）**：顶层 `block <块名>:` 键可多个；名字匹配文档名的块为**主块**（根流程，行为树执行即执行它），其余为**附属块**（可被 `ref:` 引用，供 `this/附属块` 同文档复用或 `文档/附属块` 跨文档引用）。极简裸树（整个 dict 即根块行为树）也合法。

**文档与块关系（方案 2）**：每个行为树文档可定义 1 个主块 + N 个附属块；主块可 `ref` 同文档附属块（`this/块名`）或其他文档的块（`文档名/块名`）。编辑器展示主块（可切换查看附属块属编辑器增强），保存保留全部块。

### 4.2 配置参数（工具提供, 非用户书写）

**超时 / 重试 / 浏览器 等配置参数不是用户配置, 而是工具定义的**——名称与语义固定（timeout/retry/...），全局默认来自**工具配置文件**，初始化行为树时自动注入根级 schema。**用户不在文档中书写配置参数。**

```
用户不写:
  树配置: 超时 20s ...        ← 不存在这种写法

用户需要覆盖时 (按 §5.7.5 配置参数继承规则):
  在自己的块 schema 下定义同名配置参数即可覆盖
  → 覆盖值只在当前块及以下生效
  → 未定义则向上查找祖先, 最终用全局默认
```

**为什么不由用户写配置**：配置参数是工具的运行语义（timeout/retry 的具体行为由引擎定义），写进文档会让文档耦合引擎实现，且不同作者写的块对同一配置理解不一致。引用他人块时，应尊重该块自己的配置（作者最了解自己的流程）。

### 4.3 复合节点（用户书写的主要单元）

用户直接书写行为树时，以**复合节点**（常用操作组合的语法糖）为主，减少书写负担：

```
Step        单步操作 + 验证（Sequence(Action + Condition)）
Branch      操作后多条件分支（Action + Selector 多路分流）
LoopUntil   循环直到条件成立（Repeat 带 until + 上限）
IfThenElse  直接按页面状态分支（不先操作）
Retry       失败后重试（限次）
```

**复合节点是用户书写视图，不是引擎节点**——解析行为树文档时，复合节点被展开为基础节点组合，**引擎生成的行为树对象只含基础节点，复合节点无感知**：

```
Step       = Sequence(Action + Condition)    单步操作 + 验证
Branch     = Action + Selector               操作后按顺序分流
LoopUntil  = Repeat 循环                      直到页面条件满足
IfThenElse = Selector                        直接按页面状态分流
Retry      = Repeat 循环                      直到 body 执行成功

展开时机: 行为树文档解析层 (程序化, 确定性)
  → 引擎遍历/LLM 执行时, 看到的都是基础节点
  → 复合节点只是给用户的书写便利
```

**复合节点精确语义：**

```
Step:       单步操作 + 验证 (含义明确)
            = Sequence(Action + Condition)

Branch:     操作后按结果分流
            按顺序检查 branches 的 when 条件
            → 第一个匹配的分支生效 (顺序优先)
            → 若多个 when 都满足, 走第一个匹配的
            → 无匹配则走 otherwise (若有)
            = Action + Selector(顺序检查, 第一个命中即走该路径)

LoopUntil:  循环直到页面条件满足
            每轮开头检查 until 条件
            → 条件满足 → 退出循环 (SUCCESS)
            → 条件不满足 → 执行 action → 再检查...
            → 达到 max 仍未满足 → 整体 FAILURE (安全闸)
            = Repeat(循环体=Action, 每轮先判 until)

Retry:      与 LoopUntil 基本一致, 但判断条件是"子节点是否执行成功"
            每轮直接执行 body
            → body 成功 → 退出 (SUCCESS)
            → body 失败 → 重新执行 body (重试)
            → 达到 max 仍失败 → 整体 FAILURE
            = Repeat(循环体=body, 每轮后判成功与否)
            (Retry 的终止条件是子节点执行结果, 而非页面条件)
```

**LoopUntil vs Retry 的对比：**

```
LoopUntil: 每轮【先判】until (页面条件) → 不满足才执行 action
Retry:     每轮【直接】执行 body → 成功即退, 失败重试
```

**IfThenElse：**
```
IfThenElse: 直接按页面状态分支 (不先操作)
            = Selector, 先判 if 条件 → then 分支 → 否则 else 分支
```

#### 4.3.1 Step：单步操作 + 验证

```
Step:
  action: 点击"登录"按钮            ← 自然语言描述, LLM 归约 + 定位
    CSS: button[type=submit]
  expect: 出现"工作台"              ← 验证条件 (Condition)
```

#### 4.3.2 Branch：操作后多条件分支

```
Branch:
  action: 点击"登录"
  branches:
    - when: 出现"工作台"      → 导出报表      ← 分支目标 = 块引用
    - when: 出现"密码错误"    → 重试登录
    - otherwise:              → 终止流程
```

#### 4.3.3 LoopUntil：循环直到

```
LoopUntil:
  action: 点击"批准"按钮
  until: 无"批准"按钮存在
  max: 50                     ← 循环上界 (安全闸)
```

#### 4.3.4 IfThenElse：按页面状态分支

```
IfThenElse:
  if: 存在"下载成功"提示
  then: → 完成流程
  else: → 重试下载
```

#### 4.3.5 Retry：失败重试

```
Retry:
  max: 3
  body:
    Step:
      action: 点击"下载"
      expect: 出现"下载成功"
```

### 4.4 清晰度校验标准（行为树文档是否合格）

程序解析后机器可校验的标准（不满足则打回用户修正）：

- 行为树结构**合法**（节点类型正确、嵌套关系有效）
- 复合节点**展开后合法**（展开为基础节点后可被遍历）
- 所有块引用**存在**（`ref:` 指向的块/文档可解析）
- 循环有**上界**（`max` 或 `最大循环轮数`）
- 变量契约**一致**（引用的变量在其可见作用域内，见 §5.7.4）
- 引用带输入声明的块时**输入全部绑定**且绑定目标均为声明输入（§5.7.3 绑定契约）
- 每条动作目标**可定位**（有 CSS 或有 LLM 可映射的自然语言）
- 每步**有验证条件**（Step/Branch 等的 expect/判断，否则该步成败无法判定）
- 所有条件谓词**结构可校验**（判断由 LLM 结合语义图完成，见 §5.6）

---

## 5. 两层结构：书写层与执行层

**关键区分：用户书写（结构）≠ 引擎执行（节点）。** WebOps 是自然语言驱动的工具，但**结构完全由用户控制**：

```
┌── 书写层（用户可见, 结构化行为树文档）──────────────┐
│  用户直接写行为树文档 (yaml/dict):                  │
│    block 登录:                                    │
│      inputs: ...                                  │
│      Sequence:                                    │
│        - Step(action: 填账号, expect: ...)        │
│        - Step(action: 填密码, expect: ...)        │
│    （结构=用户确定, 叶子内容=自然语言, LLM 填充）     │
└──────────────────────────────────────────────┘
              │ 程序解析 (无 LLM 转换结构)
              ▼
┌── 执行层 / 行为树对象（引擎执行, 确定性）───────────┐
│  内部行为树:                                      │
│    Block(登录):                                  │
│      Sequence:                                   │
│        - Action(type, 定位意图)                  │
│        - Condition(出现"工作台")                  │
│    （统一节点, 引擎遍历执行, 叶子由 LLM 驱动）        │
└──────────────────────────────────────────────┘
```

**引擎动作函数 = LLM 执行叶子节点时的调用接口**，是内部规范，方便将自然语言动作映射为具体执行函数。**它不是用户的书写约束——用户写自然语言,LLM 归约。**

### 5.1 引擎动作函数（LLM 的执行接口）

用户写**自然语言**描述操作，LLM 在叶子节点执行时将其归约为**引擎动作函数**调用：

```
用户写: "点一下那个绿色按钮" / "click 登录" / "填写用户名"
         └──────────────────────▶ 归约为 click() / type() / ...
```

引擎动作函数是**引擎暴露给 LLM 的执行接口**，不是用户的书写约束。以下为引擎动作函数清单（LLM 在叶子执行时选择，用户无需记忆）：

```
打开页面            → open()      （返回页面引用写入变量, §5.10）
点击                  → click()
输入 / 填写 / 键入    → type()
选择 / 选下拉         → select()
勾选 / 取消勾选       → check() / uncheck()
滚动                  → scroll()
等待                  → wait()
提取信息为变量         → extract()   （见 §5.3）
```

> **注意**：流程完成/报告（finish）不由 LLM 调用，由行为树执行流程固化（§5.8.3）——它不在引擎函数清单中。

每个动作可带可选 `CSS` 提示。

> **注意**：引擎动作函数属于执行层（§5.7.2 的 Action 节点），用户书写行为树时只写自然语言动作描述，不写函数名。

### 5.2 流程层：结构化（流转 / 变量 / 断言）

**"流程怎么走"必须精确，模糊不得** —— 这是确定性的来源。**流转由用户书写的树结构（复合节点 + 块引用）完全确定**，变量按 schema 命名空间显式管理（§5.3/§5.7.4），断言由用户显式书写（§5.5）。LLM 不决定任何流转，只在叶子节点填充理解。

### 5.3 变量：schema 命名空间机制

变量通过**带层次结构的 schema（命名空间）**管理。每次块引用产生一个独立的 schema（类似函数调用栈帧），参数写在各自的命名空间里，**同名不冲突**。

**变量引用统一为前后有界的引用符号（与自然语言明确区分）**：

```
变量引用统一为带 schema 的路径形式 (this = 当前块的 schema):
  读取:  [[get:this/amount]]            （叶子执行前程序确定性替换为真实值）
  写入声明: [[set:类型:this/amount]]     （声明本动作结果可存入该变量，值由 LLM 决定；类型 ∈ str/int/float/bool/page_ref）
  传参:   ref 处的 args: {...}          （传实参给被引用块）
  取返回: ref 处的 returns: {...}       （接收被引用块的输出）
```

**机制**：
- **读取（get）确定性**：`[[get:this/xxx]]` 出现在叶子描述中，引擎在叶子执行前从
  blackboard 读取真实值替换后注入 LLM——**LLM 看到的永远是值**，不调函数读变量。
  读取失败（变量未定义 / 越出可见作用域）→ 该叶子直接 FAILURE（程序错误）。
- **写入（set）声明**：`[[set:类型:this/xxx]]` 声明本动作的可写变量集。LLM 决定何时调用
  extract（一个 action 可多值），但 **extract 的 target 必须在声明集内**（未声明路径拒绝）。
- 用户层统一 `this` 单段（`this/变量`）；`$this` 仅为内部兼容（M3 保留，新代码用 `this`）。

#### 5.3.1 schema 的层级结构

```
主流程(T)  schema: T/
  ├── ref 登录(A)  schema: T/登录/        ← T 调用产生的子帧
  │     └── ref 输入框(A')  schema: T/登录/输入框/   ← T 不可见
  └── ref 导出(B)  schema: T/导出/        ← T 调用产生的子帧

T 可读/写:  this/xxx（仅自身帧，单段寻址）
T 不可读写: T/登录/xxx、T/登录/输入框/xxx   ← 跨帧一律不可见（经 ref args/returns 传参）
```

#### 5.3.2 可见性规则（严格、对称）

```
每个块实例只能:
  写入 → 自己的 schema（this/<名> 单段）
  读取 → 自己的 schema（this/<名> 单段）
  不可见 → 直接子块 / 祖先 / 兄弟 / 孙子 的 schema
```

**推论：传参是"逐层"的。** T 要给"输入框"传参，必须先传给登录，由登录内部转发：

```
ref 登录: args: {username: this/username}   ← T 给直接子传参
登录内:   ref 输入框: args: {值: this/值}    ← 登录负责给它自己的直接子传参
```

**取返回值 = ref returns 回收（对称）：**
```
导出块 B 完成后，把结果写到自己的帧 this/result
T 经 returns 回收: ref 导出: returns: {result: this/result}   ← 获取子块返回值的唯一途径
```

#### 5.3.3 块接口（输入输出声明）

每个命名块声明自己的接口，调用方按契约写入：

```
block 登录:
  inputs: {username: str, password: str}   ← 块需要什么 (调用方经 ref args 注入)
  outputs: login_success                    ← 块产出什么 (调用方经 ref returns 接收)
  Sequence: ...
```

**契约校验**：调用方引用块时，块声明的输入必须在 ref 处用 `args` 绑定；块声明的输出由调用方用 `returns` 按需接收。不一致 → 清晰度校验报错。

#### 5.3.4 配置参数：向上查找（与业务变量的区别）

```
业务变量 (用户定义, 命名不固定):
  严格作用域 —— 只能读/写自己的 schema（this/<名> 单段，跨帧经 ref args/returns）
  不向上查找 —— 用户必须显式写明"存到哪个 schema / 从哪个 schema 取"
  理由: 业务变量是用户定义的, 向上查找会破坏确定性

配置参数 (工具定义, 名称语义固定: timeout/retry/...):
  向上查找 —— 自己的 schema 没定义, 找最近一层祖先
  理由: 配置参数名称语义是确定的, 可复用上层
  全局默认: 工具配置文件里定义 (不写在文档里), 每次初始化时注入根级 schema
```

#### 5.3.5 类型契约

每次创建变量时声明预期类型（`str` / `int` / `float` / `bool` / `page_ref`），规则引擎据此强校验。**类型即真实存储类型**：`set` 标注驱动的 `coerce` 把网页提取值转成声明的 Python 类型后存储，转换失败则断言失败并终止。

**支持的类型集合**（M3 已落地，token 与 Python 类型映射）：

```
TYPE_REGISTRY = { str: str, int: int, float: float, bool: bool, page_ref: PageRef }
- str   任意字符串（文本 / URL / 订单号……一切字符串）
- int   真整数（校验排除布尔）
- float 数字 / 金额
- bool  布尔
- page_ref = PageRef 类型变量（页签引用，只能由 open() 产生，不能从文本转换；§5.10）
```

语义类型（金额 / 订单号 / URL / 日期 等）**不占类型位**——本质为 str/float 等基础类型；确有格式校验需求时注册为自定义类型（token + Python 类 + cast）。

```
示例:
  Step:
    action: 提取"订单金额" [[set:float:this/amount]]
    expect: [[get:this/amount]] 是数字 且 在 0~100000 之间

页面引用类型 (见 §5.10):
  open("https://.../login", save_to="this/登录页")   ← 类型: page_ref
  操作函数的页面绑定 = 当前页面变量指向的页
```

### 5.4 控制流（流转）

控制流完全确定性，**由用户书写的树结构表达**（§4.3 复合节点 + §5.7.3 块引用），不依赖 LLM 识别：

```
顺序    → Sequence / Step 串联
分支    → Branch / IfThenElse（按条件分流）
循环    → LoopUntil（带上限）
重试    → Retry（限次）
引用    → ref: 块引用（复用/跨文档）
```

**用户不写任何跳转/goto**——流转完全由树的结构化嵌套决定，这是行为树相比 goto 的核心优势。

### 5.5 断言（结果验证）

原则：断言由**用户显式书写**（"期望页面上出现什么 / 状态如何"），作为行为树的 Condition 节点求值。**不违背确定性**：判断的输入是规则生成的语义图，判断结果影响流转的方式由行为树结构确定。

**Condition 节点的求值方式（与 Action 一致，agent 式）**：

```
Condition 执行 (与 Action 相同的实现方式, 见 §5.7.2):
  输入: 节点自然语言描述 (断言) + 当前语义图
  LLM: 自主判断条件是否满足 (无需引擎介入推理)
  返回: 确定的布尔值 (结构化结果) 作为 Condition 的结果
  引擎兜底: 最大推理轮数等终止条件 (与 Action 一致的 §5.7.2.1)
```

- Condition 与 Action 的实现方式**基本一致**，唯一区别是**返回结果是确定的布尔值**（作为 Condition 节点的 SUCCESS/FAILURE 依据）
- 推理期间引擎不介入，引擎只做兜底（最大推理轮数等，同 Action）

**注意：用户没有"元素"概念。** 用户不会说"元素可见"，但会说"页面上出现'订单号：12345'""登录按钮是灰的""跳转到了个人中心"。LLM 结合语义图理解这些自然语言断言并判断真伪。

### 5.6 谓词求值

断言 / 分支条件 / 循环条件统一复用同一套**内部谓词机制**。**谓词的"理解"由 LLM 完成**（把用户的自然语言条件理解成语义图查询 + 判断真伪），**谓词的"结构"由规则引擎校验**（结构化谓词可被确定性求值）。条件必须描述**真实的页面状态变化**，避免循环无法退出（如只匹配"元素存在"而元素永不消失导致的死循环）。

> 注意：Condition 节点的判断需要 LLM 理解页面（见 §5.7.2），但这不违背确定性——LLM 判断的输入是语义图（规则生成），判断结果影响流转的方式由行为树结构（组合节点）确定。

### 5.7 行为树：流程的确定性编排结构

**行为树由用户直接书写**（§4），程序解析后由确定性编排器遍历执行。行为树是控制流的唯一表达，LLM 完全退出控制流层——只填充叶子内容。

#### 5.7.1 为什么用行为树

- **确定性**：树结构强制结构化，消除 goto 的悬空跳转/死循环问题
- **归一化**：执行节点和控制节点本质上都是节点，统一由引擎遍历
- **用户可控**：结构由用户书写，失败时用户修正文档，不依赖 LLM 猜结构
- **可扩展**：公共流程写成命名块，跨文档引用复用

#### 5.7.2 基础节点集（最小化）

**LLM 介入范围**：叶子节点（Action/Condition）需要 LLM 介入——**操作和判断都需要 LLM 理解页面**；组合节点（Sequence/Selector/Repeat）是纯程序确定性遍历，零 LLM。

```
Action      执行操作                                    叶子 · LLM介入
Condition   判断页面状态                                 叶子 · LLM介入
Sequence    顺序执行，任一失败即整体失败                组合 · 纯程序
Selector    分支选择（按条件选路径）                    组合 · 纯程序
Repeat      循环（带上限）                             组合 · 纯程序
Finish      完成/终止（报告）                          叶子（终点）· 纯程序
```

**内部节点模型字段**（解析器产物，供 M6 执行与 M8 报告）：
- `Node` 基类：`loc`（文档位置）、`frame`（所属 schema 帧标识）
- `ActionNode`：`description`（自然语言动作）、`css_hint`（可选 CSS 提示）
- `ConditionNode`：`description`（自然语言条件）+ 可选结构化字段 `target`（谓词指向对象）、`predicate`（比较谓词），供谓词结构校验
- `BranchSpec`：`condition`（为 None 表示 otherwise 兜底分支）+ `child`

**叶子节点执行（agent 式）**：Action 和 Condition 与 LLM 的交互采用 agent 式——**把节点的自然语言描述 + 当前页面语义图提供给 LLM，由 LLM 自行判断调用哪些引擎函数**（与常见 agent 交互一致）：

```
Action 执行:
  输入: 节点自然语言描述 (动作) + 当前语义图
  LLM: 自主决定调用引擎函数 (click/type/select/...)
  返回: 调用的动作函数是否执行成功

Condition 执行:
  输入: 节点自然语言描述 (条件) + 当前语义图
  LLM: 自主判断条件是否满足 (与 Action 相同的 agent 式实现)
  返回: 确定的布尔值 (结构化结果) → 作为 Condition 节点 SUCCESS/FAILURE 依据
```

- **操作和判断都依赖 LLM**，故将决策权赋予 LLM（agent 式，非函数调用式）
- 引擎函数在 Playwright 基础上封装，集中管理底层公共操作能力，方便修改/扩充（见 §5.1/§10）
- **每次 LLM 需要"看"页面时，调用语义图接口生成语义图**（§8），与行为树流程结构无关

**M6 落地细节（叶子 agent 已实现）：**

```
入口: execute_leaf(node, ctx) -> LeafResult
  LeafContext: session(M0) / engine(M5) / semantic_graph / max_rounds / timeout ...

初始语义图预取:
  循环前预取一次 semantic_graph(full, 2) 注入用户消息
  (预取失败不终止, LLM 自行决策; 预取不计入 trace.calls)

结果标记约定 (提示词要求 LLM 以标记行输出, 兼容 JSON):
  Action:     结果: 成功 / 结果: 失败
  Condition:  结果: 真 / 结果: 假 (确定布尔)
              结果: 失败 (无法确定 → LLM 侧失败)

错误来源默认分类:
  程序侧仅 FatalBrowserError + LLMConnectionError / LLMTimeoutError
  其余失败 (含全部终止) 一律 "llm"
  例外: Condition 确定布尔判断 (真/假) 为正常节点结果, error_source=None

轮数语义: max_rounds (默认 10) = 工具调用轮数上限, 第 max_rounds+1 轮请求即终止

LeafTrace: 复用 M8 契约 (llm_input/llm_reasoning/decision/calls/terminator)
```

#### 5.7.2.1 引擎与 LLM 的边界（黑盒 + 兜底）

**引擎不干预 LLM 的处理过程**——LLM 是黑盒，引擎只负责告知任务、设置终止条件、记录日志：

```
引擎职责 (兜底, 不干预):
  ① 告知任务: 叶子节点描述 + 提供 semantic_graph 能力
  ② 设置终止条件: 多轮无果 → 终止该叶子 (见下)
  ③ 记录错误日志: 按错误源分类记录 (见 §9.4)

LLM 职责 (黑盒, 自主):
  自主决定调用哪些引擎函数 (可多次调用)
  调用函数失败 → 自己看错误结果修正行为 (引擎不接管)
  直到返回结果 / 触发终止条件
```

**错误边界：**

```
LLM 函数调用返回错误 (如 click 失败):
  → 作为"工具调用结果"返回给 LLM (agent 语义)
  → LLM 自己看错误信息修正 (换函数/重新定位/换元素/放弃)
  → 引擎只统计轮数, 不判断该不该重试

程序侧致命错误 (浏览器崩溃/网络断开):
  → 无法恢复, 直接终止整个流程
  → 属于程序侧失败 (§9.4)
```

**叶子终止条件（引擎兜底，防 LLM 卡死）：**

```
任一触发 → 终止该叶子 → 记为 LLM 侧失败 → 沿行为树传播:
  ① LLM 对话轮数上限 (如 10 轮工具调用)
  ② LLM 连续 N 轮无进展 (结果未变/重复相同调用)
  ③ 单叶子执行超时 (纳入全局 timeout)
```

**terminator 取值集合（M6 已落地）：**

```
round_limit / no_progress / timeout / budget / fatal_error /
llm_connection / llm_timeout / llm_error
```

**Selector 语义严格限定为"按条件分流"，不承载兜底语义**——同一节点只允许一种理解。

**失败处理**：不设失败复合节点。节点的失败沿树传播到根，由根统一决定终止 + 报告。

**断言验证的结构**：操作 + 验证 = **Sequence 包着 Action + Condition**：

```
Sequence:
  ├── Action: 点击"登录"      ← LLM 介入 (agent 式执行)
  └── Condition: "工作台"可见  ← LLM 介入 (agent 式判断)
```

#### 5.7.3 块引用机制（ref）

**一切皆块**——匿名块（内联）、命名块（复用）、跨文档块（SubTree）统一为"块引用"：

```
块 (Block) = 一个命名或匿名的行为树子树
匿名块 (内联):  直接在父节点下写        ← 选项b (默认写法)
命名块 (定义):  定义一次, 名字引用      ← 选项c (复用)
跨文档引用:     引用其他文档的命名块     ← SubTree
```

**引用语法（统一）**：

```
ref: <文档标识>/<块名>

this/块名        当前文档内的命名块
文档名/块名      跨文档引用某块
文档名/文档名    引用整个行为树 (因为根块名 = 文档名)
```

```
流程:                          ← 根流程
  Sequence:
    - ref: this/登录          ← 当前文档的登录块
    - ref: 登录/登录          ← 登录文档的整棵树
    - ref: 导出/导出          ← 导出文档的整棵树
```

**参数绑定**（沿用 §5.3 schema 机制）：调用块时，在 ref 处用 `args: {...}` 绑定块声明的输入参数（传实参）；块输出经 `returns: {...}` 接收，写入调用方自己的 schema。**变量名严格对应块接口声明**。

**绑定契约（严格执行）**：
- 引用带输入声明的块时，**必须在 ref 处用 `args` 绑定全部声明输入**，否则清晰度校验失败（`ref.input_not_bound`）
- 绑定的目标**必须是该块声明的输入名**，绑定未声明项校验失败（`binding_not_input`）
- `Branch` / `Selector` 分支目标为**裸字符串时 = `ref: this/块名` 的简写**

**分支目标简写（§4.3 相关）**：`when: ... → 导出报表` 中的裸字符串分支目标等价于 `ref: this/导出报表`。

**执行语义**：ref 在解析期**保留为调用节点**（`RefNode`，不再内联展开），运行期由 M7 动态调用被引用块——建立独立子帧、注入 args 实参、递归执行、经 returns 回收输出；帧保留至行为树运行结束（供黑板上报）。

#### 5.7.4 schema 参数机制（帧模型）

```
每次块引用产生一个独立的 schema (命名空间, 类似函数调用栈帧):
  主流程 T:  schema T/
    ├── ref 登录 → schema T/登录/
    └── ref 导出 → schema T/导出/

可见性 (严格, 用户层单段寻址):
  每块只读写: 自己的 schema（this/<名> 单段）
  不访问:     直接子块 / 祖先 / 兄弟 / 孙子 的 schema（跨帧传参经 ref args/returns）

传参逐层传递:  T → 登录 → 登录的子块 ... (每层只处理直接子, 经 ref args/returns)
同名不冲突:    不同块的 username 在不同 schema, 互不干扰
```

> **注（用户 DSL）**：用户层已废除"直接写/读子帧"的语法（`this/子块/变量` 三段路径、`写入:` 绑定）。传参/取返回一律经 ref 的 `args`/`returns` 显式声明；ref 为**运行期动态调用**（M7 `_tick_ref`：建子帧 → 注入实参 → 递归执行 → returns 回收 → 退出子帧），帧保留至行为树运行结束（供黑板上报），激活帧控制访问权限。

#### 5.7.5 配置参数继承

```
配置参数 (timeout/retry/浏览器...):
  查找规则: 自己的 schema → 向上找最近祖先 → 全局默认
  全局默认: 来自工具配置文件, 初始化时注入根级, 不写在文档里
  理由: 配置参数名称语义固定, 可复用上层
  注意: 引用子块时, 子块自己的配置优先 (尊重流程作者设置)
```

#### 5.7.6 完整示例

```
登录.md:
block 登录:
  inputs: {username: str, password: str}
  outputs: login_success
  Sequence:
    - Step:
        action: 填 [[get:this/username]]
        expect: 输入成功
    - Step:
        action: 填 [[get:this/password]]
        expect: 输入成功
    - Step:
        action: 点"登录"
        expect: 出现"工作台"
    - Step:
        action: 提取登录状态 [[set:bool:this/login_success]]   ← 声明可写变量
        expect: 非空

导出.md:
block 导出:
  inputs: {username: str, password: str}     ← 由调用方注入
  outputs: 登录结果
  Sequence:
    - ref: 登录/登录                           ← 引入登录块
      args: {username: [[get:this/username]], password: [[get:this/password]]}
      returns: {login_success: this/登录结果}   ← 接收登录块输出
    - Condition: [[get:this/登录结果]]          ← 读 returns 接收到的输出
    - Step:
        action: 点"导出"
        expect: 出现"下载成功"

主流程.md:
block 主流程:
  Sequence:
    - ref: 导出/导出                           ← 引入导出块
      args: {username: [[get:this/账号]], password: [[get:this/密]]}
```
> 注：ref 块引用用 `args: {...}` 传实参、`returns: {...}` 接收输出；叶子内变量读写用 `[[get:this/...]]` / `[[set:类型:this/...]]`。

**Schema 流转路径追踪（主流程引用导出，导出引用登录）：**

```
主流程 schema: T/
  导出块 schema: T/导出/     ← 主流程经 args 传 T/导出/username, T/导出/password
    登录块 schema: T/导出/登录/   ← 导出块经 args 传 T/导出/登录/username (逐层转发)
    登录输出:     T/导出/登录/login_success
    导出块经 returns 收:  T/导出/登录结果  ← 写入导出块自己的 schema
```

#### 5.7.7 行为树遍历器语义（tick）

**执行是阻塞式的**——一个节点执行完才执行下一个，与真人操作一致（一步结束再下一步）。**不需要 RUNNING 状态**：

```
节点状态只有两种: SUCCESS / FAILURE
wait 节点: 内部阻塞轮询直到条件满足/超时, 返回 SUCCESS/FAILURE
组合节点按聚合规则短路 (见下)
```

**组合节点的聚合规则：**

```
Sequence  依次执行子节点, 第一个 FAILURE 即整体 FAILURE (短路)
          → 短路后后续子节点不执行
          → 全 SUCCESS 才整体 SUCCESS

Selector  按条件分流, 第一个 SUCCESS 即整体 SUCCESS (短路)
          → 子节点按顺序检查, 命中即走该路径
          → 全部 FAILURE 则整体 FAILURE
          (注意: Selector 语义是"按条件选路径", 不承载兜底)

Repeat    循环执行子节点, 带上限
          → 到达上限 → 整体 FAILURE (防死循环)
          → 条件满足 → 整体 SUCCESS
          循环条件检查时机 (对应复合节点语义, §4.3):
          → LoopUntil: 每轮【先判】until (页面条件), 不满足才执行
          → Retry:    每轮【后判】body 执行结果, 成功即退
```

**M7 落地细节（编排器已实现，含两点语义明确化）：**

```
Selector 明确化 (不承载兜底的落地):
  命中分支后子节点失败 → 整体 FAILURE, 不回落下一分支

LoopUntil 明确化:
  循环体 (action) 失败 → 整体 FAILURE 立即传播, 不吞失败继续循环

Engine.run(tree, blocks, config) -> RunResult:
  RunResult.status = success/failure; failure_reason; exec_report/trace_report
  入口校验失败路径下 exec_report/trace_report 为 None (不产出报告)

叶子执行器注入形态: (node, timeout); M0/M5 由调用方经 RunConfig 接线
超时: 按 resolve_config('timeout') 继承, 块覆盖对该块及子树叶子生效
ExecState: 复用 M8 (未新增模型)
真实执行需要 llm_config + engine (M5) 注入 (M7 不构造 M0/M5)
```

**失败传播**：叶子节点 FAILURE 沿树向上传播，由组合节点聚合，最终由根决定终止 + 报告。

**超时**：全局 timeout 在节点层面生效——单个叶子执行超时即终止该叶子（§5.7.2.1 终止条件③）。

### 5.8 引擎执行基础设施

#### 5.8.1 引擎函数集（LLM 可调用的接口）

引擎函数在 Playwright 基础上封装，集中管理底层能力，方便修改/扩充。**agent 式执行下（§5.7.2），LLM 自主决定调用哪些函数**：

```
页面函数:
  open(url)         打开页面, 返回页面引用 (写入变量, §5.9)

操作类函数 (Playwright 封装, 作用于当前页面变量指向的页):
  click(ref)          点击元素
  type(ref, text)     输入文本
  select(ref, opt)    选择下拉
  check(ref) / uncheck(ref)  勾选/取消
  scroll(direction)   滚动
  wait(条件)           等待

文件函数:
  download(ref)     触发下载 (点击下载链接/按钮), 保存文件
  upload(ref, path) 上传文件到文件选择控件

语义图函数:
  semantic_graph(范围, LOD)  获取当前页面变量指向页的语义图 (§8.8)

HTTP 函数 (两种形态, 见 §5.8.2):
  clear_requests()             清理页面请求记录
  get_response(method, url模式) 读取页面已发生的请求响应
  http_request(method, url, headers, body)  发起独立 HTTP 请求

提取函数:
  extract(ref, 目标) → 写入变量 (§5.3)
```

**引擎函数集是可扩展的**——随需求增减。底层封装供 LLM 调用的 web 操作方法集，后续可按需增加或减少（如新增 download/upload、自定义复合操作等）。

> **页面操作绑定**：所有页面操作函数（click/type/semantic_graph/...）作用于**当前页面变量指向的页面**。页面切换由变量指定（§5.9），LLM 不做页面切换决策。

**注意**：`finish` 不是引擎函数——**流程完成/报告由行为树执行流程固化**（见 §5.8.3），不由 LLM 决定调用。

**M1 落地细节（浏览器驱动层已实现）：**

```
统一返回语义: 所有操作函数返回 OpResult(ok, error, detail)
  - open/page/screenshot 等也返回 OpResult, 产物经 detail 暴露
    (open 的页面引用在 detail["page_ref"], 截图路径在 detail["path"], 失败则 ok=False)
  - 分类错误码存于 OpResult.detail["code"] (detail 作扩展位, 三字段契约不变)
  - 元素不存在/操作失败 → ok=False + error 描述 (程序侧失败, 重试有意义)
  - 浏览器崩溃/网络断开 → FatalBrowserError 异常, 终止整个流程

ref 语义:
  - ElementRef.id 在 M1 层解释为 CSS 选择器 (确定性解析, 供 LLM 操作的定位)
  - 语义图的 ref 映射 (ref ↔ DOM 元素 id) 归 M4/M5, M1 只做确定性执行
  - PageRef.id 驱动级单调递增 (跨会话不重置, 防旧引用误绑定新页)

形态A 事件泵取: Playwright sync 的事件循环只在主线程 API 调用期间运行,
  get_response/clear 前做 ~50ms wait_for_timeout 泵取 pending response 事件
  (否则页面请求的响应读不到)
```

**M5 落地细节（引擎函数层已实现）：**

```
EngineFunctions (暴露给 LLM 的 15 个函数, ENGINE_TOOLS 注册表驱动):
  构造注入: browser / filler / schema_space / current_frame
    (+ 可选 probe / graph_generator / budget_limit / page_var / download_dir / wait_timeout_ms)
  调用入口: call(name, arguments) — M6 按注册表分发

open(url) 变量名约定:
  签名无路径参数, 实现写入当前帧固定 page_var (默认 this/page, 构造可配置)
  → 契约 §5.10 的 "open(url, save_to=...)" 由上层用变量机制显式命名或配置 page_var

ref 映射 (§7.8 策略 B 落地):
  选择器优先级 = #dom_id → tag:has-text("文本") (无id有文本的链接/按钮)
                → 快照树标签路径兜底 (中间被过滤节点致路径不精确, 已知限制)
  semantic_graph 刷新作废旧 ref; 页面 URL 与快照 URL 不一致 (导航) 即过期
  拒绝区分 "无效(从未出现)" 与 "过期(历史快照出现过)"

extract 类型来源:
  目标变量声明类型按 outputs→inputs→declared 查找, 未声明按值推断,
  再经 M3 check_type 强校验

wait/download 缺省: wait_timeout_ms=30000, download_dir="."

页面绑定错误码: 无当前页面变量 → ok=False + detail["code"]=INVALID_REF

语义图失败分类:
  ProgramStageError → ok=False (NOT_FOUND)
  LlmStageError / 预算超限 → ok=False (UNKNOWN)
  FatalBrowserError → 上抛终止流程

类型复用: OpResult/FatalBrowserError 复用 M1, ToolSpec 复用 M0 (不重复定义)
```

**M5 与 M7 集成接线要求（端到端实测确认）**：

```
M5 EngineFunctions 与 M7 Engine 必须共享同一个 SchemaSpace:
  M7 Engine.run 默认每次新建 SchemaSpace (space_factory)
  M5 的 schema_space 与 current_frame 是外部注入的
  → 若两者不同实例, M5 的 open() 写页面引用时报"当前帧不可用"
  → 接线: Engine(browser=..., space_factory=lambda: schema_space) 与
    EngineFunctions(schema_space=schema_space,
                    current_frame=lambda: schema_space._current)
    必须指向同一 schema_space 实例
```

#### 5.8.2 HTTP 接口（两种形态）

自动化测试场景中，获取 HTTP 响应往往比理解页面更直观。支持两种形态：

```
形态A (页面上下文请求): 读取页面已发生的请求
  引擎自动监听页面请求 (Playwright response 事件)
  LLM 操作序列:
    clear_requests()              ← 清理记录
    click(ref)                    ← 触发请求
    get_response(method, url模式)  ← 读取匹配的请求响应
  例: 登录后读 /api/login 的响应, 判断返回的 token

形态B (独立请求): LLM 主动发起, 不经页面
  http_request(method, url, headers, body)
  认证: 由用户在流程中显式提供 (通过变量/参数传入 token/cookie)
  → 不从页面会话自动提取 (不维护 cookie, 每次执行如第一次, §5.9)
  → 认证信息由流程文档的变量机制管理 (§5.3)

选择依据: 由操作流程决定 —— "点击按钮并获取其触发的请求"用 A;
          "直接调用接口验证"用 B
```

#### 5.8.3 报告机制（执行报告 + 回溯报告）

报告与截图是一体的。**所有节点退出前都记录执行情况；Action/Condition 节点返回前额外截图**，作为该节点执行报告的一部分：

```
记录时机:
  所有节点 (整个行为树的所有节点) 退出前 → 记录该节点执行情况
  Action/Condition 节点返回前 → 引擎截图 (当前页面状态)
```

**生成两份报告：**

```
报告① 执行情况报告 (每节点执行结果 + 截图):
  每个节点:
    节点类型 / 节点描述
    执行结果: SUCCESS / FAILURE
    Action: 调用了哪个引擎函数, 是否成功
    Condition: 判断结果 (布尔)
    时间 / 页面 URL
    截图 (Action/Condition 节点的页面状态)

  用途: 概览整个流程的执行结果, 每步成功/失败 + 页面快照

报告② 回溯报告 (详细执行情况, 不含截图):
  每个节点:
    节点执行情况 (同上)
    + 该节点调用 LLM 时 LLM 的推理过程:
      提供给 LLM 的输入 (节点描述 + 语义图)
      LLM 的推理过程 (选择的函数/判断依据)
      LLM 的决策结果

  用途: 深挖问题回溯 —— 为什么某步失败/LLM 为什么这么做
```

**两份报告的关系：**
- 执行报告是"结果概览 + 截图"——快速了解流程做了什么、每步如何
- 回溯报告是"过程细节 + LLM 推理"——需要深挖时查看完整推理轨迹
- 截图只在执行报告中（Action/Condition 的页面状态），回溯报告不包含截图

**M8 落地细节（报告机制已实现）：**

```
Reporter 接口 (供 M7 调用):
  record_node(node_report)        记录节点执行情况
  start_node(node_info)           节点开始执行前调用 (§12.4 "当前执行节点"唯一来源)
  capture_screenshot(page_ref)    截图 (经注入的 screenshotter 回调包装 M1, 返回路径)
  exec_state()                    可查询执行状态 (供 M9b 轮询)
  finalize() -> ReportBundle      汇总两份报告
  构造: Reporter(run_id, report_dir, screenshotter=None, total_nodes=None)
  截图注入: screenshotter: (page_ref, path) -> OpResult (M8 不直接持有 BrowserDriver)

ExecState:
  progress 为派生属性 (已完成节点数 / 总节点数), 非存储字段; finished 后恒为 1.0
  ExecState 含 run_id / progress / current_node / completed / finished / total_nodes

LeafTrace (LLM 推理数据契约, 定义于 M8, M6 实现时对齐):
  llm_input / llm_reasoning / decision / calls / terminator

存储布局 (供 M9b 提供):
  <report_dir>/<run_id>/ 下: NNN_<desc>.png (截图) + exec_report.md + trace_report.md
```

### 5.9 浏览器会话生命周期

**每次 run 都是全新会话（从 0 开始），不持久化**——这保证流程可复现：

```
每次 run:
  全新浏览器 context (无历史 cookie/登录态)
  全流程共享这一个 context (不按块分)
  不持久化 cookie (跨运行不复用)

理由 (可复现性优先):
  第一次执行: 登录 → 生效 ✓
  第二次执行: 全新会话 → 登录流程再次生效 ✓
  若复用登录态: 第二次执行登录流程失效 → 破坏可复现性 ✗
```

**覆盖场景**：无登录 / 流程内登录 / 多标签页 / 弹窗 / 切换账号 / 下载。每次执行都是"冷启动"，行为可预测。

**注意**：跨运行复用登录态（持久化 cookie）**不在支持范围**——它破坏流程可复现性。

### 5.10 页面变量机制（多标签页）

**页面不是特殊实体，而是一类变量（页面引用）**。所有页面通过变量承载，操作哪个页面由变量指明：

```
页面 = 一类变量值 (页面引用 P1/P2/...)
  打开: open(url) → 返回页面引用, 写入变量
  传递: 和普通参数一样 (父块写子块 schema)
  切换: 变量指定, 由文档结构决定, LLM 无决策
  生命周期: 整个行为树执行结束才释放
```

**一个 schema 可有多个页面变量**（解决多页并存）：

```
主流程 T (schema T/):
  open("https://.../login", save_to="this/登录页")
  open("https://.../orders", save_to="this/订单页")    ← 一个 schema 多个页面变量

  ref: 登录块 A:
    args: {页面: [[get:this/登录页]]}         ← 传页面变量 (同普通参数)
  ref: 导出块 B:
    args: {页面: [[get:this/订单页]]}
```

**页面变量机制规则：**

```
1. 打开并存页签: open(url, save_to) — 打开 url 新建页签，把页面引用写入 save_to
   （如 [[set:page_ref:this/页面A]] 声明存页签时）；save_to 省略写默认活动页变量
2. 切回已存页签: activate(page_var) — 把已存页面变量指向的页签设为当前活动页
   （只切焦点，不新建）；描述如"切回/使用已打开的 X 页"时调用
3. 取 URL 字符串: get_url(save_to) — 存当前活动页 url 为文本（[[set:str:...]]）
4. 传递: 父块经 ref args 传子块 schema, 和普通参数传递完全一致
   → 子块要用某页面, 调用方在 ref 处用 args 传入对应页面变量 (无 LLM 推断)
5. 操作绑定: 引擎函数作用于"当前活动页"
   → "当前活动页"实现约定: 最近 activate 的页签变量；无 activate 时最近 open 的页
6. 生命周期: 页面与变量同生灭, 行为树执行结束才释放
   → 可能被子块引用 / 作为返回值传给父块, 故无法确定何时不再使用
```

**类型化 set 语法**：`[[set:page_ref:变量]]` = 存页签引用（blackboard 存 PageRef）；
`[[set:str:变量]]` = 存 url 文本。**标注即类型契约**——open 产物恒为 PageRef、
get_url 产物恒为文本，LLM 据标注选函数，写入类型由引擎函数保证。

**帧内变量单段限制**（M3 强约束）：路径在目标帧之后必须恰好一段变量名（如 `this/amount`）；含 `/` 或多段的路径（如 `this/a/b`）被拒绝——传参逐层进行（§5.3.2），不存在帧内子路径。

**LLM 视角**：LLM 每次只面对**当前活动页**的语义图（一页），跨页数据走变量、不跨页记忆。多标签页并存由 `[[set:page_ref:...]]` 命名的页面变量承载；**切换由行为树描述显式表达**（"切回 X 页"→ activate、新开/访问 → open），LLM 按描述选函数，引擎保证活动页切换确定性。

---

## 6. 与 LLM 的对接

### 6.1 接口兼容

- 用户可配置自己的 **base_url + api_key + 模型名**
- 第一版支持 **OpenAI 兼容接口**（Chat Completions / Responses）
- 覆盖 DeepSeek、Kimi、vLLM、OpenRouter 等主流开源/兼容厂商，以及 **OpenCode Go 订阅端点**（`https://opencode.ai/zen/go/v1`，`Authorization: Bearer` 鉴权，模型如 `deepseek-v4-flash`）
- 请求需携带 User-Agent 头（部分网关/Cloudflare 会拦截默认 `Python-urllib` UA）
- Anthropic / Gemini 等非兼容厂商**不在第一版范围**，后续按需适配

### 6.2 使用形态

- 无用户交互的批处理模式
- 输入：行为树文档 + LLM 配置
- 输出：执行情况报告（每节点结果 + 截图）+ 回溯报告（执行详情 + LLM 推理）

### 6.3 统一配置管理（webops/config.py）

**工具侧配置集中管理**（非用户行为树文档）。配置来源优先级：

```
① 代码内默认值（webops.config.py 中定义）
② 配置文件 webops.config.json（项目根；可用 --config 或 WEB_OPS_CONFIG 指定）
③ 环境变量覆盖（WEB_OPS_LLM_API_KEY 用于密钥安全注入）
```

**api_key 配置**：`api_key` 可直接写入配置文件 `webops.config.json` 的
`llm.api_key`（本工具内部使用，简单优先）；环境变量 `WEB_OPS_LLM_API_KEY`
存在时优先于配置文件（便于 CI/临时注入）。两种方式二选一即可，无需同时配置。

配置文件结构（`webops.config.json`）：

```json
{
  "llm":     { "base_url", "api_key", "model", "timeout" },
  "browser": { "browser_type", "headless", "timeout_ms" },
  "run":     { "timeout", "max_rounds", "no_progress_rounds",
               "session_timeout", "initial_graph_scope",
               "initial_graph_lod", "report_dir", "page_var", "budget_limit" }
}
```

加载接口：`WebOpsConfig.load(path=None)` → `to_llm_config()` /
`to_browser_config()` / `to_run_config(**overrides)`，供 CLI/服务/M9b 统一接线。

**报告目录**：`run.report_dir`（默认 `reports`，相对项目根解析），每次 run
写入 `<report_dir>/<run_id>/`（截图 + `exec_report.md` + `trace_report.md`）。

**端口约定**：本机 **8000 与 5173 端口被 NexusOps 项目占用，禁止使用**。
WebOps 使用独立端口组：M9b 后端本地开发用 **8001**（`uvicorn webops.server.main:app --port 8001`），
前端 Vite dev 固定 **5174**（`webops/frontend/vite.config.ts` 已设 `strictPort: true`），
`vite.config.ts` 的 `/api` 代理 target 指向 `http://127.0.0.1:8001`。
一键启动：项目根 `dev-restart.ps1`（`powershell -ExecutionPolicy Bypass -File .\dev-restart.ps1`）。

---

## 7. 语义图（Semantic Graph）—— 页面理解的输出契约

> 页面理解的核心目标：**把原始 DOM 加工成 LLM 容易理解、包含页面有效信息、体现元素关联关系的格式。** 这个输出称为**语义图**。

### 7.1 设计动机

直接让 LLM 阅读原始 DOM 是不够可靠的（不可靠、token 昂贵、元素关联关系散落在结构里）。语义图是对原始页面信息的一次**意义投影**：它不是 DOM 的复制品，而是只保留"对定位/提取/断言三个任务有用的信息"并显式表达元素间关联的结构化视图。

### 7.2 两个消费者、一个内容模型

语义图有**两个消费者**，但底层是**同一份内容模型**：

```
┌─ 引擎（内部对象模型）──────────────────────┐
│ 结构化的图: 节点 + 带类型的边, 可机器校验   │
│ ref 映射 / 断言求值 / 关联计算 都在这层      │
└──────────────────────────────────────────┘
   ▼ (序列化)
┌─ LLM（看到的文本形式）────────────────────┐
│ 只为可读性服务, 不要求可被机器解析          │
└──────────────────────────────────────────┘
```

**关键原则：**
- 引擎持有完整结构化图（对象模型）；LLM 只看到一份为阅读优化的序列化文本
- **不要试图让文本格式同时兼顾"机器可解析"和"LLM 好读"**——会两头不讨好
- 序列化只为 LLM 的可读性优化，不必承担被引擎解析的职责

### 7.3 节点：统一为元素节点

语义图以**元素为基准**——进图单位是元素，**文本内容作为元素的属性记录**，不存在独立的数据节点：

```
元素节点 (Element):
  代表: DOM 元素 (可交互 / 结构 / 纯文本承载)
  例:  input, button, table, row, span, p, td
  属性: role, 作用(purpose), 状态, 文本(text), 
       ref, 坐标(视觉关联的承重属性)
  文本 = 元素的属性 (text), 不单独成节点

  "¥98.00" → td 元素的 text 属性
  "欢迎回来,张三" → span 元素的 text 属性
```

**关键点：**
- **一切内容都归属于某个元素**——文本永远是元素的属性，没有"游离数据"
- 元素按性质可分为：可交互（操作目标）、语义容器（层级骨架）、纯文本承载（携带信息）
- 步骤目标是操作时关注可交互元素；目标是获取内容时关注携带文本的元素
- **携带文本的元素进图 = 文本所归属的元素进图，文本作为属性记录在该元素上**

### 7.4 空间组织：分层结构（B 方案）

元素按**语义容器层级**组织（见 §8.4），携带文本的元素作为叶子挂载在所属层级：

```
语义容器 (form / table / row / 导航)
  └─ 元素 (含文本属性)
     例:
     ROW R1
       td: text="ORD-001"  (订单号)
       td: text="¥98.00"   (金额)

  → 看到 ROW R1 就知道它的子元素含 金额="¥98.00" (文本属性)
```

- 文本是元素的属性，随元素挂载在语义容器层级中
- **不存在"游离数据"**——一切文本都属于某个元素，元素按规则进图并挂载

### 7.5 语义图数据结构（字段定义）

语义图由**图根 + 节点 + 边**组成。以下为字段定义（引擎内部对象模型的契约，LLM 看到的是其序列化文本）。

#### 7.5.1 图（Graph）

```
{
  type: "semantic-graph",
  version: "0.1",
  page: { url, title, page_type },
  regions: [Region...],          // 区域节点
  elements: [Element...],        // 元素节点 (含文本属性)
  edges: [Edge...],              // 关联关系
  changes: [Change...]           // 可选: 相对上次快照的变化
}
```

#### 7.5.2 区域节点（Region）

页面的大块作用域，提供分组与上下文。

```
{
  kind: "region",
  id: "R1",
  ref: "[F1]",                    // LLM 可见引用
  region_type: "form" | "table" | "dialog" | "list" | "nav" | "section",
  label: "登录区",                 // 区域语义 (LLM 每次生成时填充)
  scope: "...",                    // 作用域描述（可选）
  bounds: { x, y, w, h },         // 包围盒（用于视觉关联）
  child_elements: ["E1","E2"...], // part-of 边的便捷索引
}
```

#### 7.5.3 元素节点（Element）

**所有进图的元素**（可交互 / 语义容器 / 纯文本承载）共用此结构。文本作为属性记录，不单独成节点。

```
{
  kind: "element",
  id: "E1",
  ref: "[1]",                      // LLM 引用锚点（唯一）
  role: "textbox" | "button" | "link" | "select"
      | "checkbox" | "table" | "row" | "column"
      | "text" | "paragraph" | ...,
  purpose: "用户名输入框",          // 元素作用 —— 由 LLM 每次生成时填充
                                  //   (如: 用户输入框/密码输入框/导航页签)
  state: {                          // 当前状态 (程序化实时读取)
    value: "",                      // 输入值 / 选中值
    checked: false,                 // 复选框
    disabled: false,
    visible: true,
    text: "",                       // 元素的文本内容 (含纯文本承载元素)
    selected: "",                   // 下拉当前选中
  },
  options: ["全部","待审批",...],     // 下拉选项（role=select 时）
  bounds: { x, y, w, h },          // 坐标（视觉关联的承重属性）
  pair_candidates: [...],          // 可选: related-to 候选
  confidence: "explicit" | "inferred" | "ambiguous",
}
```

**两个由 LLM 每次填充的字段**（语义图生成接口的 LLM 阶段产出，见 §8）：
1. **purpose（元素作用）**：该元素在页面中的角色——用户输入框 / 密码输入框 / 导航页签 / 提交按钮 / 金额文本...
2. **related-to 关联打分**（见 §7.5.5）：该元素与其他元素的相关性

其余字段（role/state/options/bounds）由**程序化阶段**实时读取。**文本（state.text）是元素的属性**，随元素进图。

> **关于"数据"**：页面承载的值/文本（金额、订单号等）都是**携带文本的元素的 text 属性**。提取信息 = 从元素的 text 属性中提取（LLM 结合 purpose/关联定位目标元素）。

#### 7.5.4 文本承载元素（Text-bearing Element）

携带文本的元素（span/p/td 等）与普通元素共用同一结构（§7.5.3），**文本记录在 state.text 属性中**：

```
例 (td 元素):
  {
    kind: "element",
    id: "E9",
    ref: "[9]",
    role: "cell",
    purpose: "金额",            // LLM 填充
    state: { text: "¥98.00" },  // 文本 = 元素属性
    ...
  }
```

- 文本承载元素不是独立节点类型，就是元素节点，text 是其属性
- 提取/断言针对携带文本的元素：定位目标元素 → 读其 text 属性

#### 7.5.5 边（Edge / 关联关系）

三种核心关联（§7.7）。**关联是带权重的、多对多的**——不强制一对一匹配，每条关联都携带分数与理由：

```
{
  id: "ED1",
  type: "related-to" | "part-of" | "value-of",
  from: "E2",                      // 源节点 id
  to:   "E1",                      // 目标节点 id
  origin: "visual" | "structural", // 来源：视觉几何 / DOM 结构
  confidence: "explicit" | "inferred" | "ambiguous",
  score: 0.0 ~ 1.0,                // 关联强度（相对排序用，无绝对阈值）
  reason: "...",                    // 为何相关（LLM 判定理由 / 规则依据）
  detail: "视觉邻近: 左侧",          // 推断依据（可选）
}
```

**关联的多对多特性：**
- 一个文本节点可关联多个控件（不同权重）
- 多个文本节点可关联同一控件（不同权重）
- 弱关联（低分）也保留——分数代表"相对相关程度高低"，不设绝对阈值

**分数与理由由 LLM 每次生成语义图时填充**（§8），反映当前页面元素间的真实关联。每次完整生成，无跨快照累积（§9.5）。

#### 7.5.6 变化段（Changes，可选）

相对上次快照的状态变化，帮助 LLM 理解流转与引擎断言：

```
{
  type: "appeared" | "disappeared" | "changed",
  node_id: "D1",
  summary: "表单消失, 出现弹窗 D1",
}
```

#### 7.5.7 字段定义汇总表

元素节点字段（统一节点类型，文本为属性）：

| 字段 | 元素节点 | 说明 |
|---|---|---|
| id / ref | ✓ | 唯一标识 + LLM 引用锚点 |
| role | ✓ | 元素角色 (程序化) |
| purpose | ✓ | 元素作用 (LLM 每次填充) |
| state (value/checked/text/...) | ✓ | 元素当前状态, 含文本属性 (程序化) |
| options | ✓(select) | 下拉选项 |
| bounds (坐标) | ✓ | 视觉关联承重属性 |
| confidence | ✓ | 显式/推断/歧义 |

> 文本承载元素（span/p/td）与普通元素同一结构，文本在 state.text 中。

### 7.6 LLM 视角：层次树序列化契约

引擎对象模型（§7.5）通过**序列化规则**渲染成 LLM 可读的文本。LLM 视角的语义图 = 层次树风格文本。

#### 7.6.1 序列化原则

```
1. 从属关系编码进排版 (part-of)
   树形缩进表达层级, 不靠括号标注
2. 兄弟节点按视觉顺序排列 (从左到右、从上到下)
   树的层级来自结构, 兄弟顺序来自视觉 —— 化解"视觉顺序 vs DOM顺序"张力
3. 只渲染对 LLM 有用的字段
   bounds/confidence 等引擎内部字段不进文本 (绝对像素坐标不进文本)
4. ref 是 LLM 的动作引用锚点
   引擎渲染时分配, LLM 原样引用
```

**空间方位标注（§8.3 ③ 扩展）**：元素/区域行尾输出**稳定方位词**（九宫格：
`top`/`middle`/`bottom` × `left`/`center`/`right` 组合，如 `(页面top-right)`），
由引擎用元素中心相对视口计算。**这是空间语义，不是像素坐标**：

- 方位词相对稳定——页面小幅滚动/布局变化不改变"右上角"语义（像素坐标会变）
- 供 LLM 理解位置指令（"点击右上角的登录按钮"、"第5行右侧的查看按钮"）
- 仅当元素跨视口边界时才可能改变方位；每次 `semantic_graph` 生成都基于
  当前视口重新计算（M4 无缓存，§8.8）
- 需要视口尺寸（M1 快照携带 `viewport`）时才输出；无 viewport 时不输出

#### 7.6.2 渲染规则：节点 → 行

**区域节点（Region）→ 区域头**

```
REGION <region_type> <ref>   <label>
   例:  REGION FORM F1  作用域=登录区
        REGION TABLE T1  说明="订单列表, 共 10 行"
```

**元素节点（Element）→ 元素行**

```
<缩进> <role> <ref> <purpose>  [附加状态]
   例:  FIELD  [1] textbox "用户名输入框"  value=""  (关联: "用户名" 0.9·视觉邻近)
        ACTOR  [4] button  "登录按钮"
        LINK   [5] "忘记密码链接"

role 前缀映射:
  FIELD  → 输入类 (textbox/input)
  ACTOR  → 可点击动作 (button/submit)
  LINK   → 链接
  CHECK  → 复选框/单选
  SELECT → 下拉
  ROW    → 表格行
  CELL   → 单元格(框架)
```

**状态渲染（state 子集）:**
```
value="当前值"     输入值
text="..."        按钮/链接文本 (作用已含时省略)
checked / 未选中   复选框
disabled           禁用
选项=[a,b,c]      下拉选项
```

**文本承载元素 → 字段并列行**

```
<缩进> <role> [<ref>] <purpose>="<text>"
   例:  金额="¥98.00"  订单号="ORD-001"  状态="待审批"
   (文本承载元素: td/span/p, text 属性即其内容)
```

#### 7.6.3 关联关系的呈现方式（三种边各不同）

```
part-of    → 编码为缩进层级           (无需额外标注)
value-of   → 文本承载元素并列在所属元素行内  (字段语义直接可见)
related-to → 括号标注在目标元素行尾     (语义关联, 带分数, 需显式说明)

例:
  FIELD [1] textbox "用户名"  value=""   (related-to: "用户名" 0.9·视觉邻近·高置信)
  FIELD [2] textbox "密码"    type=password
```

- related-to 标注格式：`(related-to: <来源元素> <分数>·<推断依据>)`
- 分数与理由由 LLM 每次生成语义图时填充（§7.5.5），反映当前页面元素间的真实关联

#### 7.6.4 完整示例

```
PAGE: 订单列表  URL=https://orders.example.com/list

REGION TABLE T1  说明="订单列表, 共 10 行"
  表头: 订单号 | 客户 | 金额 | 状态 | 操作
  ROW R1
    订单号="ORD-001"  客户="甲公司"  金额="¥98.00"  状态="待审批"
    ACTOR [4] button "批准"
  ROW R2
    订单号="ORD-002"  客户="乙公司"  金额="¥152.00"  状态="待审批"
    ACTOR [5] button "批准"
```

```
PAGE: 登录页  URL=https://example.com/login

REGION FORM F1  作用域=登录区
  FIELD [1] textbox "用户名输入框"  value=""      (related-to: "用户名" 0.9·视觉邻近)
  FIELD [2] textbox "密码输入框"    type=password (related-to: "密码" 0.9·视觉邻近)
  CHECK [3] "记住我"  未选中
  ACTOR [4] button "登录按钮"
  LINK  [5] "忘记密码链接"
```

#### 7.6.5 引擎字段 → LLM 文本映射表

| 引擎对象字段 | 是否进 LLM 文本 | 呈现方式 |
|---|---|---|
| id | 否 | 内部标识 |
| ref | 是 | `[N]` 引用锚点 |
| role | 是 | 行首前缀 (FIELD/ACTOR/...) |
| purpose | 是 | 行内引号 |
| state.value | 是 | `value="..."` |
| state.text | 是 | 文本承载元素显示为 `作用="文本"` |
| state.checked/disabled | 是 | `checked/禁用` |
| options | 是 | `选项=[...]` |
| bounds | 否 | 不进文本(引擎内部) |
| confidence | 条件 | 仅歧义时标注 |
| 边 | 部分 | part-of=缩进, value-of=并列, related-to=括号标注(带分数) |

### 7.7 关联关系（边）：三种核心关系

语义图中的关联关系本质上是**为了让 LLM 更好理解页面**。经收敛，保留三种核心关系：

```
1. related-to (语义关联) —— 视觉语义关联
   related-to 表示两个元素之间存在语义关联, 带权重, 多对多
   权重反映"相对相关程度高低", 不强制一对一
   例: span"用户名" 与旁边的 input 有强关联(它就是用户名的输入框)
       与远处的另一个 input 只有弱关联(低分, 保留但不影响定位)

2. part-of (从属关系) —— 结构关联
   节点属于某个区域/容器
   例: 按钮属于表格行; 表格框架 (table→row→column) 帮助 LLM 理解
   row 之间本质上有语义关系(同一种事物的不同取值), 由 DOM 框架确定
   保留框架元素的从属关系有助于 LLM 理解

3. value-of (数据归属) —— 字段语义理解
   文本承载元素归属于某个字段/列 (其文本 = 该字段的值)
   例: 表头"金额"列 → 该列单元格元素的文本 ¥98.00
   注意: related-to/part-of/value-of 都是元素间的关联 (文本是元素属性)
```

**核心判断（related-to 的修正）：**
- **视觉邻近 ≠ DOM 邻近**。真实页面中，`span"用户名"` 和对应 input 可能在 DOM 里相隔多个层级、在不同子树（grid/flex 布局很常见），但人眼看到它们相邻、是"一对"
- 因此 `related-to` 的**证据来源是视觉几何（bounding box），而非 DOM 结构**——这是它区别于 part-of（结构关联）的根本
- **不是一对一匹配**：related-to 是多对多、带权重的关联。定位时不找"唯一匹配"，而是找"相对权重最高的关联"

**打分（LLM 每次生成时填充）：**
- LLM 判断元素间的关联并打分（相对排序，无绝对阈值）+ 记录理由
- **分数与理由每次生成时填充**（§8.7），无跨快照累积

**边的两种来源：**

```
结构关联 (来自 DOM 树)        视觉/语义关联 (来自布局)
part-of   从属关系            related-to 语义关联(加权多对多)
value-of  表格框架派生的列关联  (需坐标/结构支撑)
(DOM 父子关系直接可得)
```

**遗留问题（已定案）：**
- related-to 的"语义"部分由 **LLM 每次生成时判断**（见 §8.7）
- ~~序列化阅读顺序~~：已定案 —— 树层级来自结构(part-of)，兄弟节点按视觉顺序排列（见 §7.6.1）

### 7.8 与 LLM 的引用机制（ref 桥）

文本快照与引擎对象之间的映射**不依赖 LLM 猜**，而是引擎持有确定性 ref 表：

```
文本快照:  FIELD [1] textbox "用户名"
引擎对象:  { id: 17, role:"textbox", name:"用户名" }
            ↑
        [1] ↔ {id:17} 由引擎的 ref 映射表确定
```

**信任边界：**
- **语义理解归 LLM**：LLM 判断"用户说输入用户名 → 我看到 [1] 叫用户名 → 选 [1]"
- **引用解析归引擎**：`[1] → DOM 节点 → 函数调用` 全确定性，不信任 LLM

**ref 稳定性策略（两个选项，倾向 B）：**

```
A. 稳定 ref: 尽力让同一元素跨快照保持同一 ref
   (引擎用 DOM 特征/路径跟踪元素身份)
   ✓ LLM 可跨步骤引用记忆  ✗ 页面动态变化时身份跟踪很难出错

B. 会话内 ref 即用即弃 (推荐)
   LLM 每次动作前必须先取最新快照, 用最新 ref
   引擎强制: 页面状态一变化, 旧 ref 全部失效
   ✓ 无身份跟踪负担, 确定性高  ✗ LLM 不能依赖跨步骤记忆
```

B 与确定性原则一致：LLM 不跨快照记仇，每次动作前重新取快照、取新 ref（呼应"元素定位必须运行时实时做，不编译期缓存"）。

### 7.9 序列化示例（LLM 视角）

> 完整的 LLM 视角层次树示例已见 §7.6.4。本节保留早期平铺示例供对照演进。

```
PAGE: 登录页  URL=https://example.com/login

REGION FORM F1  作用域=登录区
  FIELD  [1] textbox "用户名输入框"  value=""        (related-to: "用户名" 0.9·视觉邻近)
  FIELD  [2] textbox "密码输入框"    type=password   (related-to: "密码" 0.9·视觉邻近)
  CHECK  [3] "记住我"  未选中
  ACTOR  [4] button "登录按钮"
  LINK   [5] "忘记密码链接"
```

### 7.10 关联关系的属性

- 每条边可携带**来源**（结构 / 视觉）与**置信度**
- related-to 的分数与理由由 LLM 每次生成时填充（§8.7）
- 定位失败时（LLM 侧失败）提示用户补充 CSS 提示（§9.4/§9.7）

---

## 8. 语义图生成（Semantic Graph Generation）

> 页面理解的核心目标：把原始 DOM 加工成语义图。本章定义**如何从原始页面生成语义图**。

### 8.1 三个信息源：各回答一个问题

```
┌─ DOM 树 (HTML) ────────────────┐
│ 回答: 结构问题                  │
│ 父→子→兄弟 层级 (part-of 的来源) │
│ 框架元素: form/table/tr/td/ul   │
│ 显式属性: type/placeholder/id    │
│ 局限: 不知道视觉关系, 不知道可见性 │
└────────────────────────────────┘
┌─ Accessibility Tree ───────────┐
│ 回答: 语义问题                  │
│ 浏览器算好的 role/name/state     │
│ 显式关联: label-for / aria       │
│ 局限: 不含布局, 不含隐式视觉关联, │
│       长页噪音大                 │
└────────────────────────────────┘
┌─ 空间/布局 (geometry) ──────────┐
│ 回答: 视觉问题                  │
│ 位置/尺寸/可见性/包围盒           │
│ 视觉邻近→related-to 候选         │
│ 阅读顺序 (从左到右、从上到下)      │
│ 局限: 纯几何, 无任何语义          │
└────────────────────────────────┘
```

**关键判断：三个信息源描述的是"同一批节点"的三个侧面**（DOM 节点、a11y 树节点、几何包围盒在浏览器里都指向同一 DOM 元素）。融合不是"三个信号投票"，而是**把三个侧面合并到同一个节点上**。

### 8.2 融合原则：DOM 为骨干，其余为富集

```
每个语义图节点 =
    DOM 身份(骨干)     +  a11y 语义(富集)   +  几何空间(富集)
   (id/层级/框架/内容)   (role/name/state/     (bounds/可见性/
                        显式关联)              邻近/阅读顺序)
```

为什么 DOM 是骨干而不是 a11y：
- DOM 包含**全部内容**（文本、所有节点），a11y 是派生且丢内容的（只有 accessible name）
- DOM 有精确的层级结构，是 part-of 和框架元素的来源
- a11y 只是**语义增强器**，不能独立成图

### 8.3 两阶段生成流水线

语义图生成分为**两阶段**——程序化阶段 + LLM 填充阶段：

```
程序化阶段 (每次都跑, 纯程序):
  ① DOM 爬取 → 候选节点集
     分类: 可交互 / 框架 / 内容
     过滤: 隐藏/装饰/零尺寸
  ② 结构富集: role / 层级 / part-of (来自 DOM 树)
  ③ 几何计算: bounds / 可见性 / 阅读顺序 / 空间方位 (九宫格方位词, §7.6.1)
  ④ 程序化值: input 当前值 / checked / disabled / 文本 (实时读取)

LLM 填充阶段 (每次都做):
  ⑤ 填充每个元素的 purpose (元素作用)
  ⑥ 填充元素间的 related-to 关联打分与理由

  输出: 完整语义图 (§7.5 结构)
```

**两个阶段各司其职：**
- 程序化阶段提供**客观事实**（结构/位置/状态/值）——无需理解，程序可靠获取
- LLM 填充阶段提供**语义理解**（元素作用/关联）——需要理解，由 LLM 完成

### 8.4 候选元素筛选规则

**哪些元素进语义图**——从 LLM 阅读角度出发，语义图按**语义容器层级 + 元素归属**组织，而非照搬 DOM 深度。**进图单位是元素，文本作为元素属性（§7.3）**：

```
筛选规则:
  ① 必须进 (叶子): 可交互元素 + 携带文本的元素
     可交互: input/button/a/select/textarea/checkbox/radio...
     携带文本: 有可见文本的节点 (承载信息/purpose 依据)
     → "携带文本的元素进图" = 文本所归属的元素进图
     → 该文本作为属性 (state.text) 记录在该元素上, 不单独成节点

  ② 语义容器进图 (层级骨架/区域): 
     form / table / dialog / nav / section / fieldset / ul(列表)...
     → 作为层级骨架, 提供区域边界 (REGION)

  ③ 纯定位 div/span: 不占独立层级
     → 只用于确定元素归属 (通过 DOM 祖先关系)
     → 不烧 token

  ④ 层级深度: 语义容器嵌套层数, 由 LOD 控制 (见 §9.5)

  ⑤ 过滤: 隐藏 / 零尺寸 / aria-hidden 始终剔除
```

**为什么按语义容器层级（而非 DOM 深度）：**

```
层级呈现 (推荐) vs DOM 深度 (照搬):
  REGION FORM F1                       div
    FIELD [3] 用户名输入框               div
    FIELD [6] 密码输入框                   span input
    ACTOR [4] 登录按钮                  div
  REGION NAV N1                           span input
    LINK [5] 忘记密码                    div
                                          span a
  → 层级 = 语义容器                       → 层级 = DOM 深度
  → 紧凑, 语义清晰                       → 深且噪音多
```

**关键认知——层级承载关系：**
- 共享语义容器 = 两个元素属于同一组（关系由层级体现，不需要 LLM 额外推理）
- 例：`[3]` 和 `[6]` 同属 FORM F1 → LLM 一眼看出它们是同一表单的字段
- 语义容器提供"区域边界"——LLM 知道"表单结束、导航开始"

**区域与纯结构的区分：**
- **区域（REGION）**：有语义角色的容器（form/table/dialog/nav/section...）
- **纯结构**：div/span 等纯定位元素，不占层级，只用于确定归属

### 8.5 LLM 介入：每次生成都填充语义

> 本节省的是**语义图生成**这一层面（§8）的 LLM 介入。行为树执行层面的 LLM 介入（Action/Condition 叶子节点）见 §5.7.2，两者是不同层面。

**语义图生成的每次调用，LLM 都介入填充语义字段**：

```
程序化阶段: 纯程序, 零 LLM (结构/位置/状态/值)
LLM 填充阶段: 每次都需要 LLM (purpose + related-to 打分)
```

**为什么每次都要 LLM**：
- **purpose（元素作用）**需要理解页面（"这是用户名输入框还是密码输入框"）——规则引擎无法可靠推断
- **related-to 关联打分**依赖语义理解（两个相邻元素是否构成"标签-控件"对）——规则只能给几何候选，语义判断需 LLM
- 这是语义图的核心价值：**LLM 理解的产物**，不是规则的廉价推断

**与旧设计的区别**：之前设想"规则优先、仅歧义时 LLM 兜底"——但规则无法可靠地填充语义，故改为**每次生成都由 LLM 填充语义字段**。代价是 token 开销，但换来语义图的正确性（符合 §9.5 的原则：语义图必须正确反映页面）。

### 8.6 purpose 填充（LLM）

对每个候选元素，LLM 结合结构/位置/邻近文本/显式关联，填充其**作用**：

```
对 input#1:  邻近有"用户名"文本 → purpose: "用户名输入框"
对 input#2:  type=password     → purpose: "密码输入框"
对按钮:       文本"登录"       → purpose: "登录按钮"
对导航链接:    文本"报表中心"   → purpose: "报表中心导航页签"
```

purpose 是 LLM 对每个元素"在页面中是什么"的理解，是定位（§9）和提取（§10）的依据。

### 8.7 related-to 关联打分（LLM）

LLM 判断元素间的关联，填充带权重的关联边：

```
LLM 输出 (对元素间的关联):
  span"用户名" → input#1  分: 0.9  理由: "这是用户名输入框的标签, 视觉紧邻左侧"
  span"用户名" → input#2  分: 0.2  理由: "相距较远, 且 input#2 已被'密码'语义占用"

关联多对多特性:
  多对一:   "用户名"+"请输入用户名" 都关联 input#1 (不同权重)
  一对多:   "用户名"文本 关联 input#1(强) + input#2(弱)
  弱关联:   "用户名" → input#2 权重0.2 (低到不影响定位, 但保留信息)
```

**分数与理由由 LLM 每次生成时填充**（§7.5.5），无跨快照累积。

### 8.8 语义图接口（统一入口）

```
semantic_graph(范围, LOD):
  ① 程序化阶段: DOM 爬取 + 结构 + 几何 + 程序化值
  ② LLM 填充:   每个元素 purpose + related-to 打分
  ③ 返回:       完整语义图 (§7.5)

调用方式 (agent 式, §5.7.2):
  LLM 在叶子执行中通过 semantic_graph(范围, LOD) 获取语义图
  LOD 决定信息量 (见 §9.5)

无缓存: 每次调用完整生成, 保证语义图始终反映当前页面 (见 §9.5)
```

**参数定义：**

```
范围 (范围): 语义图覆盖的页面区域
  全页 / 指定区域 (区域 id, 如 F1 / 表格 T1)
  → 控制"广度"维度 (见 §9.5 ②)
  → 区域 id/ref 规则: form→F1/[F1], row→R1 等; 范围参数匹配 id 或 ref (去括号后)

LOD (Level of Detail): 语义图的精细程度
  四维参数组合 (深度/广度/属性/关联), 划分 LOD-0~3 (见 §9.5)
  → 控制"深度/属性/关联"维度
```

**M4 落地细节（语义图生成已实现）：**

```
接口签名: semantic_graph(page_ref, scope, lod, *, probe, filler, budget_limit=None)
  probe/filler/budget_limit 由 M5 引擎函数层接线注入

两阶段失败语义:
  爬取失败 (M1 DOM 快照) → ProgramStageError (程序侧, 可重试)
  LLM 填充失败 (含 M0 连接异常) → LlmStageError
  FatalBrowserError 保持传播 (致命, 终止流程)

related-to 打分输入边界:
  LLM 的关联打分只接受几何候选预筛集内关联 (候选集为 LLM 输入边界)

LOD 裁剪时机:
  深度/广度裁剪在 LLM 填充【前】 (省 token)
  属性/关联裁剪在【后】作用于输出 (省 token)
  part-of/value-of 边始终保留 (结构关联不随 LOD 裁剪)

预算: 超限抛 SemanticGraphBudgetExceeded, 不静默截断

返回: 完整语义图 + RefMap (ref ↔ 元素 id 映射表, 随图返回,
      供机器侧校验/断言求值用, §7.8 策略 B)
```

### 8.9 现实复杂度与当前范围边界

**当前明确不处理的场景（第一版范围外）：**

```
iframe 场景:   当前不处理跨 iframe 的语义图与操作
   → 语义图只覆盖主文档, 不合并 iframe 内元素
   → 操作不路由到 iframe 内元素

动态刷新元素:  当前不处理懒加载/虚拟滚动/动态渲染
   → 默认页面加载后所有元素都已就绪
   → 不处理"滚动才加载更多行"等动态场景
```

**已知限制（诚实标注）：**

```
可见性陷阱:   display:none / opacity:0 / aria-hidden / 视口外
Shadow DOM:  可被 a11y 扁平化, 但层级信息可能丢
Canvas 渲染:  无 DOM, 非视觉方案彻底盲区 ← 必须接受的限制
超大页面:     token 预算 → 靠 §7.6 蒸馏 + 分级呈现
```

---

## 9. 操作指令生成与元素定位（执行模型）

> 语义图（§7/§8）与引擎动作函数（§5）的衔接：**引擎函数决定"怎么操作"（方法），LLM 决定"对哪个元素"（目标）。** 本章定义执行阶段的核心——操作指令的生成与元素定位。

### 9.1 衔接点：引擎函数执行 + LLM 自主决策

agent 式执行（§5.7.2）下，引擎函数提供"能力"，LLM 决定"怎么用"：

```
"输入用户名"
    │
    ├─ ① LLM 获取语义图: semantic_graph(范围, LOD)
    ├─ ② LLM 结合描述定位: 在语义图中找到"用户名"输入框 [1]
    └─ ③ LLM 自主选择引擎函数: type([1], "admin")
                       │
                       ▼
          引擎执行 type() ← 引擎函数只负责执行, 选择权在 LLM
```

- **引擎函数提供"能力"**：click/type/select/... 是引擎封装的执行能力（§5.8）
- **LLM 自主决策**：结合描述 + 语义图，LLM 决定用哪个函数、对哪个元素
- **定位独立于引擎函数**：无论 click/type/select，定位逻辑是共用的——"在语义图里找与描述匹配的元素"

**定位同时服务于 Action 与 Condition**：Action 定位目标元素以操作；Condition 定位目标元素以判断状态（如"工作台"元素是否存在、是否可见）。两者的定位机制相同，只是后续动作不同。

### 9.2 定位任务的输入与输出

agent 式执行下，定位由 LLM 在叶子执行中自主完成（结合节点描述 + 语义图）：

```
定位的输入:
  ① 语义图 (当前页面状态, 含元素作用字段)
  ② 节点自然语言描述 (动作/条件: "用户名" / "登录按钮")

定位的输出:
  一个 ref (指向语义图中 LLM 认定的目标元素)

LLM 定位的依据 (结合语义图判断):
  ① 元素作用匹配:  语义图元素的作用字段 ≈ 节点描述 ("用户名输入框" → [1])
  ② 角色匹配:      引擎函数期望角色 vs 元素 role (type→textbox)
  ③ 关联强度:      related-to 分数 (若多个候选)
  ④ 上下文:        区域/邻近文本 (辅助消歧)
```

定位正是 LLM 把"描述映射到语义图节点"的判断过程——依赖语义图的元素作用字段（§7.5.3）与关联打分（§7.7）。

### 9.3 定位意图（Positioning Intent）

**定位意图不结构化**——采用 agent 式执行后（§5.7.2），LLM 直接结合节点描述与语义图自行判断目标，**不强制输出结构化的检索条件**：

```
用户写: "在用户名输入框输入 admin"
LLM 执行: 看语义图 → 结合描述 → 自主定位"用户名"输入框 [1] → 调用 type([1], "admin")
```

理由：操作/判断多数是简短描述，提取结构化条件收益有限，反而增加 LLM 负担。定位的正确性由语义图的**元素作用字段**（§7.5.3）保障——每个元素由 LLM 标注了作用（如"用户名输入框"），定位即"在语义图中找作用匹配的元素"。

### 9.4 错误分类：按错误源，而非断言/异常

**失败不区分"断言失败 vs 执行异常"，而是按错误源划分**——这决定处理方式：

```
按错误源分类:
  ┌─ LLM 侧失败: LLM 无法处理导致的
  │   定位失败 / 语义理解失败 / 判断失败
  │   → 属于 LLM 的能力边界
  │   → 处理: 重试无意义, 报告用户, 提示完善文档/补 CSS
  │
  └─ 程序侧失败: 确定性程序执行错误
      浏览器崩溃 / 网络超时 / 元素不存在(程序确认)
      → 属于基础设施/环境的确定性错误
      → 处理: 重试有意义 (网络抖动/元素未渲染), 等待重试
```

**定位失败明显属于 LLM 侧**。此分类比"断言/异常"更本质——两种失败的处理方式完全不同：LLM 失败重试无意义，程序失败重试有意义。

### 9.5 语义图分级（LOD, Level of Detail）

"控制语义图信息量"不是单个开关，而是**四个独立维度**的参数化组合：

```
① 深度: 语义容器嵌套层数 (见 §8.4)
   表层(区域头+顶层元素) → 深层(嵌套的语义容器内部结构)
② 广度: 纳入候选集合的元素数量
   只含直接候选 → 含邻近上下文 → 整个区域
③ 属性: 每个节点携带字段的多少
   仅role+名称 → +value → +相关文本 → +全部
④ 关联: related-to 边的详尽程度
   无 → 只列高分边 → 全部分数+理由
```

**属性维度具体定义（M4 已落地）：**

```
minimal  = role + 名称 (purpose)
standard = minimal + value
rich     = standard + options + 全量文本
full     = 全部字段
```

**LOD 分级（四维参数的组合）：**

```
LOD-0 (最简):  深度=0, 广度=只含候选, 属性=仅role+名, 关联=无
               用途: 页面概览, 快速了解有什么
LOD-1 (标准):  深度=1, 广度=区域, 属性=含value, 关联=高分边
               用途: 正常定位
LOD-2 (详细):  深度=2, 广度=整区域, 属性=含相关文本, 关联=全部分数+理由
               用途: 复杂判断/提取字段
LOD-3 (全量):  全部展开
               用途: 疑难/兜底
```

**生成方式（每次完整生成，无缓存）：**

```
每次调用 semantic_graph(范围, LOD) 都完整生成:
  ① 程序化阶段: DOM 爬取 + bbox + 可见性 + 程序化值 (每次都跑)
  ② LLM 阶段:   填充每个元素的作用 + 关联打分 (每次都做)

无缓存, 无指纹, 无失效机制
```

**为什么不用缓存**：任何页面变化（含 input 值变化）都可能影响 LLM 后续判断，**语义图必须始终正确反映当前页面**——宁可多花 token，绝不返回可能过期的语义图。故每次调用都完整生成，确保正确性优先。

**程序化值（如 input 当前值）也在每次生成中实时读取**，保证语义图反映最新页面状态。

### 9.6 多轮定位机制

定位是**由 LLM 主导的多轮搜索**——在 agent 式执行中（§5.7.2），LLM 通过多次调用语义图接口获取不同范围/LOD 的语义图，逐步缩小或调整视角，直到锁定目标。**搜索控制权完全归 LLM**：该缩小还是放大、看哪里、看多细，都由 LLM 自主决定。

```
多轮定位 = LLM 多次调用 semantic_graph(范围, LOD):
  缩小范围 (从大区域 → 候选区域 → 目标元素)
  或加深细节 (LOD 逐级提升)
  或放大回溯 (回到更大范围重新选择)
  直到定位成功 / 判定失败
```

**每一轮 LLM 决定两件事：**
1. **下一轮看哪里**（范围：哪个区域/节点）
2. **下一轮看多细**（LOD：什么级别）

**关键认知——必须有"放大"（回溯）：**
- 只有缩小是"单向收窄"，一旦早期判断错（如选错区域）就走进死胡同，永远找不到
- 完备搜索必须允许回溯：`全页面 → 表单A → (找不到) → 退回全页面/换区域 → 表单B → 找到`
- 定位的本质是搜索，完备的搜索必须有回溯能力，故放大动作不可少

### 9.7 定位终止条件

定位是叶子执行内部的一个子过程（§5.7.2 agent 式执行中，LLM 通过多次调用 semantic_graph 定位目标）。**定位终止条件是叶子终止条件（§5.7.2.1）的一个子集**——引擎提供安全边界（防死循环），但不干预 LLM 的搜索判断：

```
定位终止条件 (二选一先触发):
  ① 轮数上限: 超过 5 轮 → 定位失败
  ② 结果未变检测: 连续 2 轮 LLM 给出相同判断但无法确认
     → 视为卡住, 定位失败
  ③ token 预算: 累计语义图 token 超限 → 定位失败

叶子终止条件 (§5.7.2.1) 包含并覆盖以上定位终止
```

**第 ② 条捕获"原地打转"**：如果 LLM 连续两轮看了同一范围、得出同样的不确定结论，说明已无法进步，再给轮次也是浪费。

**终止后的处理：**

```
定位失败 → 分流:
  关键目标元素 → 报告用户, 提示补 CSS/完善文档 (LLM 侧失败, §9.4)
  非关键元素   → 放弃定位, 动作跳过或标记
```

### 9.8 执行模型总结

```
用户直接书写行为树文档 (yaml/dict, 复合节点 + 块引用 + schema 变量)
      │
      ▼
⓪ 初始化 (§5.9): 创建全新浏览器 context (从 0 开始, 无持久化)
      注入全局默认配置到根级 schema
      │
      ▼
① 程序解析行为树文档 → 内部行为树对象
      结构不合法 → 返回用户修正  ← 清晰度校验
      │
      ▼
② 执行: 编排器按行为树结构确定性遍历 (阻塞式, §5.7.7)
      组合节点 (Sequence/Selector/Repeat) ← 纯程序, 零 LLM
      叶子节点 (Action/Condition)         ← LLM 介入 (agent 式)
      │
      ▼
③ 叶子节点: agent 式执行 (§5.7.2)
      LLM 结合节点描述 + 语义图, 自主决定调用引擎函数
      引擎只兜底: 终止条件 (§5.7.2.1) / 错误日志
      │
      ▼
④ LLM 需要看页面时 → 调用 semantic_graph(范围, LOD) 获取语义图 (§8.8)
      每次完整生成, 始终反映当前页面变量指向的页
      │
      ▼
⑤ LLM 自主定位 (多轮 semantic_graph 缩小/放大) → 确定目标 ref
      │
      ▼
⑥ LLM 调用引擎函数: type(ref, ...) / click(ref) / ... → 引擎执行
      │
      ▼
⑦ 节点退出前记录报告 (§5.8.3):
      Action/Condition 返回前 → 引擎截图
      所有节点 → 记录执行情况 + LLM 推理 (两份报告)
      → SUCCESS 走下一步 / FAILURE 沿树传播
      → 失败按错误源分流 (LLM侧 vs 程序侧)
      │
      ▼
⑧ 行为树执行结束 → 释放 context (含所有页面变量与页面)
```

---

## 10. 待解决：页面理解（后续单独讨论）

本契约已定义的**"双形式定位 + 变量提取 + 断言"**都依赖 WebOps 的核心能力 —— **LLM 对页面的理解**。语义图的**内容模型**（§7）、**生成方案**（§8）、**执行模型与元素定位**（§9）、**行为树编排**（§5.7）已定义，剩余待解决项如下。

### 10.1 待办清单（涉及页面理解，需在后续方案中解决）

1. **变量提取的实现**：LLM 如何从"自然语言 + 语义图"中提取字段并写入 schema 变量（衔接 §9 定位机制与 §5.3）
2. **断言求值的实现**（核心难点）：用户没有"元素"概念，如何把"页面上出现'订单号：12345'""登录按钮是灰的"这类自然语言断言，让 LLM 结合语义图可靠判断真伪（Condition 节点 agent 式执行，见 §5.7.2）
3. **语义图生成接口的实现**：§8 两阶段（程序化 + LLM 填充）落地——候选元素筛选规则（§8.4：可交互+携带文本必进、语义容器作层级骨架、纯结构归属性）、DOM 爬取/bounds/程序化值 + LLM 填充 purpose/related-to 打分；LOD 控制（深度=语义容器嵌套层数）；token 预算
4. **引擎函数集的实现**：§5.8 落地——open()/操作类函数（Playwright 封装）、semantic_graph 接口、HTTP 函数（页面上下文/独立请求两形态）、extract
5. **叶子节点 agent 式执行的提示词设计**：如何让 LLM 结合节点描述 + 语义图可靠决策（选函数/定位/判断），见 §5.7.2
6. **行为树文档解析器**：§4 行为树文档格式的落地——yaml/dict 解析、复合节点展开为基础节点、块引用解析、schema 变量绑定、清晰度校验、确定性遍历器
7. **复合节点的字段 schema 细化**：§4.3 复合节点（Step/Branch/LoopUntil/IfThenElse/Retry）的精确语义已定（§4.3），需细化 yaml 字段 schema（when/until/max/body 等具体写法）
8. **报告机制实现**：§5.8.3——所有节点退出前记录执行情况、Action/Condition 返回前截图、生成两份报告（执行报告含截图 / 回溯报告含 LLM 推理）
9. **行为树遍历器实现**：§5.7.7——阻塞式执行、SUCCESS/FAILURE 聚合、组合节点短路、失败传播、超时
10. **浏览器会话管理实现**：§5.9——每次 run 全新 context、无持久化、全流程共享
11. **页面变量机制实现**：§5.10——open() 打开页面引用、页面变量传参、当前页面变量绑定、生命周期（行为树结束释放）
12. **叶子终止条件实现**：§5.7.2.1——LLM 轮数上限、连续无进展检测、单叶子超时

---

## 11. 命令形态（规划）

```
webops check 文档.yaml    # 阶段一: 解析行为树文档, 清晰度校验, 交互式修正
webops run   文档.yaml    # 阶段二: 批处理执行, 输出执行报告 + 回溯报告
```

---

## 12. 模块划分与架构（分模块实施依据）

> 本章定义 WebOps 的模块划分、各模块功能、依赖关系与实施顺序，**作为后续分模块实现的依据**。每个模块可独立实现与测试。

### 12.1 模块总览

```
M0  LLM 客户端          无依赖           最早实现
M1  浏览器驱动           无依赖           独立
M2  行为树文档解析器      纯逻辑           易测
M3  schema 命名空间      纯逻辑           易测
M4  语义图生成           M1+M0
M5  引擎函数层           M1+M4+M3
M6  叶子 agent 执行      M0+M5
M7  编排器 + 遍历器      M2+M3+M6+M8
M8  报告机制             M1 + 可查询执行状态
M9a 前端 UI             M9b
M9b 行为树管理系统后端    M2+M7+M8 (内嵌引擎)
```

### 12.2 模块功能与依赖

#### M0 LLM 客户端
```
功能:
  封装 OpenAI 兼容接口 (base_url/api_key/模型名 配置)
  提供统一的 agent 会话调用 (多轮工具调用)
  管理 LLM 上下文 / token
依赖: 无
测试: mock HTTP 响应 / 连接真实 API 均可独立测
```

#### M1 浏览器驱动
```
功能:
  context/page 管理 (每次 run 全新 context, §5.9)
  操作函数: open/click/type/select/check/scroll/wait (§5.8.1)
  文件函数: download/upload
  HTTP 监听: clear_requests/get_response (§5.8.2 形态A)
  截图能力 (§5.8.3)
  页面变量 → page 的绑定 (§5.10)
依赖: 无
测试: 真实浏览器, 独立于其他模块
```

#### M2 行为树文档解析器
```
功能:
  yaml/dict 解析 (§4)
  复合节点展开为基础节点 (§4.3)
  块引用解析 (ref: this/文档名/块名, §5.7.3)
  schema 变量绑定声明提取 (§5.3)
  清晰度校验 (§4.4)
依赖: 无 (纯逻辑)
测试: 输入文档 → 输出内部行为树对象, 纯函数测试
```

#### M3 schema 命名空间
```
功能:
  帧模型: 块实例的独立命名空间 (§5.7.4)，ref 运行期动态调用建帧
  严格作用域: 读/写自己（this/<名> 单段，跨帧经 ref args/returns）(§5.3.2)
  配置参数继承: 向上查找 (§5.3.4)
  页面变量机制 (§5.10)
  变量类型: TYPE_REGISTRY (str/int/float/bool/page_ref) (§5.3.5)
依赖: 无 (纯逻辑)
测试: 纯数据结构操作, 作用域/继承规则单测
```

#### M4 语义图生成
```
功能:
  候选元素筛选规则 (§8.4)
  程序化阶段: DOM 爬取 + 结构 + 几何 + 程序化值 (§8.3)
  LLM 填充阶段: purpose + related-to 打分 (§8.5/8.6)
  语义图接口 semantic_graph(范围, LOD) (§8.8)
  序列化: 引擎对象模型 (§7.5) → LLM 层次树文本 (§7.6)
依赖: M1(浏览器/DOM) + M0(LLM填充)
测试: 程序化阶段可独立测, LLM 填充可 mock
```

#### M5 引擎函数层
```
功能:
  暴露给 LLM 的函数集 (§5.8.1): 操作/文件/语义图/HTTP/提取
  页面操作绑定: 当前页面变量 (§5.10)
  函数可扩展: 随需求增减
依赖: M1 + M4 + M3
测试: 各函数独立测试 (mock 语义图/M3)
```

#### M6 叶子 agent 执行
```
功能:
  Action/Condition 的 agent 式执行 (§5.7.2)
  引擎兜底: 终止条件 (轮数/无进展/超时) (§5.7.2.1)
  定位: 多轮语义图缩小/放大 (§9.6/9.7)
  错误边界: 函数失败归 LLM / 致命错误归引擎 (§5.7.2.1)
依赖: M0(LLM) + M5(引擎函数)
测试: mock M5 函数, 验证 agent 决策/终止条件
```

#### M7 编排器 + 遍历器
```
功能:
  行为树遍历 (阻塞式, §5.7.7): SUCCESS/FAILURE 聚合, 短路
  组合节点: Sequence/Selector/Repeat
  失败传播 + 超时
  触发叶子执行 (M6) + 记录报告 (M8)
  维护可查询的执行状态 (供 M9b 轮询, §12.4)
依赖: M2(树) + M3(schema) + M6(叶子) + M8(报告)
测试: mock 叶子执行, 验证遍历/聚合/传播逻辑
```

#### M8 报告机制
```
功能:
  所有节点退出前记录执行情况 (§5.8.3)
  Action/Condition 返回前截图
  执行报告: 每节点结果 + 截图
  回溯报告: 执行详情 + LLM 推理 (不含截图)
  维护可查询的执行状态 (进度/当前节点/已完成报告)
依赖: M1(截图) + 叶子执行数据
测试: mock 节点执行数据, 验证报告生成
```

#### M9a 前端 UI
```
功能:
  行为树编辑器: 拖拽节点 + 填写信息 → 生成含复合节点的行为树文档
  行为树管理: 列表/查看/修改/删除 (CRUD)
  执行报告页: 轮询执行状态, 实时渲染节点进度 + 截图
依赖: M9b (纯前端)
```

#### M9b 行为树管理系统后端
```
功能:
  行为树文档 CRUD API (存储/管理)
  清晰度校验 (保存时, 复用 M2)
  执行触发: 调引擎.run (M7)
  执行状态查询 API: 返回进度/已完成节点/截图 (供前端轮询)
  截图/报告存储与提供
依赖: M2 + M7 + M8 (引擎作为库内嵌, §12.3)
测试: mock M7 执行, 验证 API 与文档管理
```

### 12.3 引擎内嵌形态

**引擎作为库被"行为树管理系统"后端调用**——M9b 与引擎同一进程：

```
[行为树管理系统进程]
  ├── M9b 后端服务 (HTTP API + 前端交互)
  ├── M7 引擎 (作为 Python 库直接 import/调用)
  └── 执行任务: 后端调用 引擎.run(行为树) → 轮询执行状态

内嵌的好处:
  简单 (无进程间通信)
  共享内存 (行为树对象/报告数据无需序列化传输)
  执行状态查询方便 (同一进程直接读)
```

### 12.4 前端执行报告的实时展示（轮询）

**采用定时轮询**（非流式）——前端定时查询执行状态并更新：

```
执行流程:
  ① 前端点击"执行" → 调用 M9b 执行接口
  ② M9b 触发引擎.run (M7, 异步后台执行)
  ③ M7 执行时维护"可查询执行状态":
      当前进度 / 当前执行节点 / 已完成节点报告 / 截图路径
  ④ 前端每 1 秒轮询执行状态接口
  ⑤ 前端按节点实时渲染: 节点成功/失败 + 该节点截图
  ⑥ 执行完毕 → 展示完整执行报告

选择轮询的理由:
  实现简单 (普通 HTTP 请求, 无 WebSocket 基础设施)
  节点执行粒度下 (秒级), 1秒轮询接近实时
  失败/异常也能被轮询捕获
```

**M9b 落地细节（管理后端已实现）：**

```
报告根位置: M9b 服务端报告/截图固定落盘 data/reports/（覆盖 §6.3 默认 reports），
  runs.report_path 只存相对路径; 报告经 GET /api/reports/{path} 提供（路径白名单防穿越）

run_id 语义: POST /run 返回的 run_id 为 runs 表自增 id（非引擎内部 run_id），
  引擎报告目录按服务端 run_id 对齐

轮询终态: 执行中 state 的 completed 含全部节点报告（优先读引擎内存终态快照）;
  进程重启后回落 DB 终态（completed 为空，完整报告走 /report）
  执行中获取报告: /report、/trace 返回 200 + {"status":"running"}（非 425/409）

启动恢复: 服务启动时 running 与 pending 记录均置 failure（failure_reason="interrupted"）

doc_id/帧对齐: 执行时按内容实际根块名解析，库内 name 可与根块名不同
```

### 12.5 前端行为树的复合节点视图

**用户看到的始终是含复合节点的行为树，引擎执行的是基础节点**：

```
前端视角 (用户看到):      后端执行 (引擎看到):
  行为树文档 (含复合节点)     行为树对象 (纯基础节点)
    Step / Branch /           Sequence(Action+Condition) /
    LoopUntil / Retry...      Selector / Repeat...
         │                           ▲
         │ 保存为文档                 │ M2 解析时展开 (§4.3)
         ▼                           │
  行为树文档 (含语法糖) ── 展开 ──▶ 基础节点行为树

用户始终看到复合节点 (可读性好)
引擎始终执行基础节点 (确定性)
```

**清晰度校验位置**：
- 前端保存时校验一次（友好提示用户修正）
- 后端执行前再校验一次（确保可执行）

### 12.6 依赖关系图

```
        ┌──── M0 LLM ────┐
        │                ▼
M2 文档解析   M6 叶子agent  ◄─── M5 引擎函数 ◄─── M4 语义图生成
        │         │                       ▲          ▲
        ▼         ▼                       │          │
M3 schema ◄─── M7 编排器 ────► M8 报告 ◄───┘          │
        ▲         │                       M1 浏览器 ───┘
        └─────────┘
                 │
                 ▼
        ┌──────────────┐
        │  M9b 后端服务  │ ◄── M9a 前端 UI
        │  (内嵌引擎)   │
        └──────────────┘
```

### 12.7 实施顺序

```
阶段1 (无依赖, 可并行):  M0 LLM / M1 浏览器 / M2 解析器 / M3 schema
阶段2 (依赖M1):         M4 语义图生成 / M8 报告
阶段3 (依赖M0+M4+M3):   M5 引擎函数层
阶段4 (依赖M0+M5):      M6 叶子执行
阶段5 (整合):           M7 编排器 (串联一切)
阶段6 (前端):           M9a 前端 UI + M9b 后端服务
```

---

*本文档为 v1.9 契约初稿，供进一步讨论修订。*
