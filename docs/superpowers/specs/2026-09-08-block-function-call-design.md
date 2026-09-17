# 引用块函数式参数传递与类型系统统一设计

> 日期：2026-09-08
> 状态：设计稿（待用户审阅）
> 范围：M2 解析 / M3 schema / M5 引擎 / M6 叶子执行 / M7 编排 / M8 报告 / M9a 前端（黑板）/ docs 契约 §5.3.2 §5.7.3 §5.7.4
> 关联：变量引用重构（get/set）、页面变量机制补全（page_ref）

## 背景与动机

用户对现有"块引用参数传递"设计提出质疑。现状（契约 §5.7.3/§5.7.4）传参依赖 **blackboard + 引用块层级权限**：父块用 `{{set:this/导出/username}}` 写入子块 schema，子块读自己帧；子块输出写自己帧，父块事后 `{{get:this/导出/login_success}}` 读留存子帧。存在两个问题：

1. **块输入输出不明确**：一个引用块到底需要多少外部参数、返回多少给外部，运行时无强制、仅解析期纸面校验。
2. **参数传递方法模糊**：完全依赖父块手工把参数搬进/搬出子帧（三段 `$this/块/名` 路径），执行期无"调用→绑定实参→执行→返回"机制。

用户期望**直接使用类似编程语言的参数传递机制**：块明确定义输入/输出，父块调用子块时显式传实参、显式接收返回值。代价是牺牲部分灵活性换取明确性。

此外，探索中暴露**类型系统分裂**：动作标注 token（`page`/`string`）与 schema 存储类型（中文键：文本/整数/页面引用…）分属两套拼写；且类型只是"校验谓词"而非真实存储类型（`set:int` 存进去的未必是真 `int`）。用户要求类型 token 统一、存储类型真实化（存储的就是 Python 真实类型），并收敛基础类型集合。

## 目标

1. **块 = 函数**：命名块声明 `inputs`（形参+类型，全部必填）与 `outputs`（输出名，值由块内 set 决定）。
2. **ref = 函数调用**：`args`（显式传实参）+ `returns`（显式接收返回值）；跨块数据唯一通道。
3. **blackboard 局部化**：业务变量访问范围限制在命名块内（局部变量语义）；配置参数保留块层级继承（向上查找）。
4. **帧即调用栈**：每次 ref 动态建帧、返回即销毁；父块不再事后读子帧。
5. **运行时动态调用**：ref 保留为调用节点，遍历到时才建帧/进子块/返回销毁；支持同块多次引用、未来并行节点（帧实例隔离）。
6. **类型统一 + 真实化**：token↔Python 类型注册表，校验用 `isinstance`；set 标注驱动 cast；基础类型收敛为 str/int/float/bool + 自定义注册类型。
7. **DSL 关键字英文化**：语法字面量全部英文。

## 设计

### 1. 完整 DSL 语法（英文化）

```yaml
# 登录.md
block 登录:
  inputs: {username: str, password: str}      # 形参 + 类型
  outputs: login_success                        # 输出名（值由块内 set 决定）
  Sequence:
    - Step:
        action: 填 [[get:this/username]]        # 读形参注入的局部变量
        expect: 输入成功
    - Step:
        action: 填 [[get:this/password]]
        expect: 输入成功
    - Step:
        action: 提取登录状态 [[set:str:this/login_success]]   # 声明输出
        expect: 非空

# 导出.md（跨文档引用嵌套调用）
block 导出:
  inputs: {username: str, password: str}
  outputs: report
  Sequence:
    - ref: this/登录
        args: {username: this/username, password: this/password}  # 裸路径=引用父帧局部变量
        returns: {login_success: this/登录成功}    # 子块输出 → 本块局部变量
    - Condition: [[get:this/登录成功]] == true
    - Step:
        action: 点"导出" 提取下载状态 [[set:str:this/report]]
        expect: 出现"下载成功"

# 主流程.md
block 主流程:
  Sequence:
    - ref: 导出/导出
        args: {username: "admin", password: this/密}
        returns: {report: this/导出报告}
    - Step:
        action: 校验 [[get:this/导出报告]]
        expect: 含"下载成功"
```

**变量语法形态**（统一 `[[ ]]` 分隔）：
- 写入声明：`[[set:<类型>:this/<名>]]` —— **类型必填**，set 标注是变量存储类型的唯一权威来源；引擎按标注 coerce 后存储，无法转换 → 断言失败
- 读取插值：`[[get:this/<名>]]`（不带类型，纯读）或 `[[get:<类型>:this/<名>]]`（带类型则运行时校验，不匹配断言失败）
- args / returns 值：裸路径 `this/<名>` 或字面量（传参语义已明确，无需 get/set 标注）
- 分隔符由旧 `{{ }}` 改为 `[[ ]]`：规避 f-string（`{` 需转义）与正则量词的冲突；`[[ ]]` 在中英文动作描述中几乎不误撞

**类型权威**：变量存储的真实 Python 类型**由 set 标注决定**（Python 变量必须有类型）。引擎函数写库（extract/open/get_url 等）若目标已有声明类型（set 标注 / 块 inputs / 已写 declared）则按该类型 coerce，转换失败报错而非静默存 str。M6 提示词须告知 LLM 每个可写变量的目标类型，使其按需提取原始值供存储时转换。

**关键字映射**：

| 现在（中文） | 改为 | 作用 |
|---|---|---|
| `操作块 X:` | `block X:` | 块定义前缀 |
| `输入:` | `inputs:` | 形参声明（dict: 名→类型） |
| `输出:` | `outputs:` | 输出声明（串/列表） |
| `写入:`（ref 绑定） | 废除 → `args:` / `returns:` | ref 传参 / 接收 |
| 类型中文键（文本/整数/…） | str/int/float/bool + 自定义 | 统一类型 token |
| set 标注 `page`/`string` | `page_ref` / `str` | 并入统一类型注册表 |

废除项：
- `写入:` 键与 `ParamBinding` 三段目标路径语法
- 跨帧寻址 `$this/块/名`（写子块输入）
- 读子块输出 `{{get:this/子块/名}}`
- 旧 `$` 前缀兼容路径
- 旧 `{{ }}` 变量分隔（改 `[[ ]]`），叶子描述内变量读写全部迁移

### 2. 类型系统（收敛 + 真实化）

**原理**：set/get/blackboard 使用同一套类型名；类型即真实存储类型；校验统一 `isinstance`。

```python
# autobranch/schema/types.py（重构）
@dataclass
class TypeSpec:
    token: str                  # DSL 引用名：str/int/float/bool/page_ref
    py_type: type               # 真实 Python 类型
    cast: Callable | None       # 网页提取值 → 该类型的转换；None = 不可由文本产生

TYPE_REGISTRY: dict[str, TypeSpec] = {
    "str":      TypeSpec("str", str,     lambda v: str(v)),
    "int":      TypeSpec("int", int,     _to_int),      # "123" → 123
    "float":    TypeSpec("float", float, _to_float),    # "1.5" → 1.5
    "bool":     TypeSpec("bool", bool,   _to_bool),     # "true"/"1"/"on" → True
    "page_ref": TypeSpec("page_ref", PageRef, None),    # 只能由引擎函数 open() 产生
}
```

- `check_type(token, value)`：`isinstance(value, TYPE_REGISTRY[token].py_type)`，不匹配断言失败。
- `coerce(token, raw)`：set 标注驱动的类型转换，网页 str → 目标真实类型；`cast is None`（如 page_ref）→ 拒绝文本转换。
- **写库 coerce 接线**：extract 等写库函数若目标已有声明类型（set 标注 / 块 inputs / 帧 declared）则 `coerce` 后存储（转换失败 → 断言失败，终止流程）；无声明才 `infer_type`。
- 自定义类型扩展：注册表加一行（token + Python 类 + cast）。首个自定义 `PageRef`（页签引用，现有类收敛于此）。
- Python 陷阱：`bool` 是 `int` 子类，`int` 校验须排除 bool（内聚在 check/coerce 层）。
- `infer_type`（仅无声明时的后备）按 Python 值类型：str/int/float/bool/PageRef——业务变量类型主源是 set 标注。
- 不再存在的"业务语义类型"（金额/订单号/日期/URL 等）——本质为 str/float 等，不占类型位；确有校验需求时注册为自定义类型（带 cast）。

### 3. 执行模型（运行时动态调用 + 帧即调用栈）

```
主流程/                        ← 根帧（block 主流程），运行时帧实例
  ├── ref 导出 (实例) → SchemaFrame#N   每次调用独立实例
  │     └── ref 登录 (实例) → SchemaFrame#M
  └── ref 导出 (再次) → SchemaFrame#K   同块多次引用各自独立
```

**帧身份 = 运行时帧实例对象，不用块名路径命名**。`this/<名>` 中 `this` 指当前执行中的帧对象。变量名只需在单帧内唯一。未来并行节点：每个分支持有各自帧实例，天然隔离，无需预设计数命名。

**ref 调用执行顺序**：
1. 在父帧上下文求值 `args` 每个实参（裸路径 `this/xxx` → 父帧局部值；字面量）。
2. 按被调用块 `inputs` 声明类型 `coerce`/`check_type`；失败 → ref 断言失败（终止流程）。
3. 建子帧：`enter_block`，cast 后形参写入子帧（`this/形参名`）。
4. 动态执行子块树（其内部叶子用 `[[get:this/形参]]` 读取）。
5. 子块 SUCCESS → 取声明的 `outputs` 对应值，按 `returns` 映射写父帧局部变量；FAILURE → 不写 returns，失败向上传播。output 的赋值来源 = 块内叶子 `[[set:...:this/<名>]]` 或嵌套 ref 的 `returns`；某 output 在运行中未被赋值（如分支未走）→ SUCCESS 时该 output 为空/未定义，报告标注"输出未赋值"提示，不阻断流程。
6. 退出销毁子帧（帧数据不留存，父块无法事后读）。

**帧生命周期规则**：
- 帧只在 ref 调用时创建；块内匿名内容共享所在块帧（不额外建帧）。
- 帧在调用返回后立即销毁。
- 配置参数仍沿帧链向上查找（exit 前可用父帧链）；业务变量不向上查找。

### 4. 校验（两阶段）

**阶段一：文档清晰度校验（运行前，静态）**
- ref 目标块存在（missing_doc / missing_block）
- `args` 键 ⊆ 子块 `inputs` 声明；`inputs` 全部必填（缺 → input_not_bound）
- `returns` 键 ⊆ 子块 `outputs` 声明
- `inputs` 声明的类型 token 已注册
- 实参路径 = 本帧裸路径 `this/<名>`（单段，无跨帧）
- ref 图静态环检测（沿用现有 cycle / recursion_depth）
- **output 全赋值**：块声明的每个 `outputs` 名，其块体内必须存在赋值点——叶子 `[[set:...:this/<名>]]` 或嵌套 ref 的 `returns` 目标含 `<名>`；缺失 → `output_not_set`（对称于 input_not_bound）。仅要求"存在赋值点"，**不分析分支路径**：走某分支未赋值时运行期 SUCCESS 该 output 为空/未定义并在报告提示，不阻断流程。
- **get 已定义**：块内 `[[get:this/<名>]]` 读取的变量必须是本块 `inputs` 声明、块内 `[[set:...:this/<名>]]` 目标或 ref `returns` 目标；否则 → `scope.get_undeclared`。output 声明不构成 get 源。

**阶段二：运行期（动态调用时）**
- 实参在父帧求值（裸路径 `this/<名>` → 实际值；字面量）
- coerce 到形参声明类型（失败 → 断言失败，终止流程）
- returns 仅在子块 SUCCESS 时写父帧

### 5. 作用域规则（替代 §5.3.2）

```
每块只读/写：
  · 本块帧内变量 this/<名>
    —— 来源：args 注入形参、块内叶子 set 局部变量、本块声明的 outputs
  · 不读任何其他帧（无子块帧、无父帧业务变量）

变量寻址 = 单段（this/<名>），废除所有跨帧多段路径。
跨块数据唯一通道：ref args / returns。
配置参数 = 唯一例外：向上沿帧链查找。

页面引用（page_ref）也走 args/returns 传递，不因浏览器全局状态而例外。
blackboard 黑板展示保留各调用帧局部变量（调试视角），但运行期 get 不可跨帧寻址。
```

### 6. 模块影响与改造点

| 模块 | 现状 | 改动 |
|---|---|---|
| M2 parser/document.py | 中文键、ref `写入:`、静态声明 | 语法英文化；`inputs` dict 类型化；`args`/`returns` 解析；废除 `写入:` |
| M2 parser/models.py | `BlockDecl.inputs/outputs` 纯名字 | `inputs` 带类型（名→类型）；ref 调用记录 args/returns |
| M2 parser/expand.py | ref 静态展开、帧路径静态写死 | ref 保留为调用节点不再展开；帧树信息改运行时；静态环/目标/参数键校验保留于此（阶段一） |
| M3 schema/space.py | `enter/exit_block`、帧数据保留、current_page 帧内 | 帧销毁语义；动态实例化；配置沿激活帧链查找 |
| M3 schema/types.py | 中文谓词类型表 | 收敛为 TypeSpec 注册表 + isinstance + coerce |
| M3 schema/models.py | `PageRef` | 保留为第一个自定义类型（注册表 token page_ref） |
| M3 schema/path.py | 多段帧路径解析 | 收敛单段 `this/<名>` |
| M5 engine/engine.py | 写当前/直接子帧、输出声明类型查找 | 变量写当前帧；get_url/open 等 save 用真实类型（PageRef/str） |
| M6 leaf executor | `set_decls` 校验 + get 替换 | get/set 单帧寻址；set 标注驱动 coerce |
| M6 prompts | 类型化提示 page/string | 同步 token（page_ref/str），输入类型化提示 |
| M7 orchestrator/traverser.py | 静态 `node.frame` 驱动 enter/exit | 动态调用执行器：ref 节点运行时递归进入子块树 |
| M8/M9a | 报告/黑板展示 | 帧实例展示（如 `登录#N`），运行期不可跨帧 |
| docs contract.md | §5.3.2/§5.7.3/§5.7.4 | 同步为新作用域/函数式调用/类型注册表 |

### 7. 不做的事（范围外 / YAGNI）

- 并行节点：本轮只保证设计兼容（帧实例隔离），不实现。
- 形参默认值/可选参数：全部必填。
- 类型校验语义类型（金额/订单号/URL/日期）：不占类型位，作为自定义类型扩展点保留。
- 配置参数的函数化：保留层级继承，不作为函数传参。
- 块级显式 return 提前结束：输出 = SUCCESS 时声明的 outputs 值打包。

## 测试清单

- **M2 解析/静态校验**：新语法（block/inputs dict/outputs/args/returns）解析；废除语法报错；类型 token 已注册校验；args⊆inputs / returns⊆outputs / inputs 全必填 / output 全赋值（缺失 → output_not_set）；环检测保留。
- **M3 类型系统**：注册表 isinstance 校验（str/int/float/bool/page_ref）；coerce 成功与失败（"123"→int、"abc"→int 失败）；page_ref 拒绝文本 cast；bool/int 子类边界。
- **M5/M6 单帧寻址**：get/set 单段；跨帧寻址被拒；set 标注 coerce 驱动。
- **M7 执行器（集成，真实 LLM/桩）**：
  - 单层调用：ref args 注入→块内 get 读形参→输出 returns 回收
  - 嵌套调用：导出→登录 跨文档
  - 同块多次引用：两次 ref 同块互不干扰（独立帧）
  - FAILURE 传播：子块失败不写 returns
  - 配置参数沿帧链继承；业务变量不跨帧
  - 页面变量走 args 传递、activate 于子块内
- **前端**：黑板展示帧实例变量；类型 token 英文。
- **E2E**：前端执行多块嵌套调用行为树，查看执行与报告符合预期。
- **回归**：既有 769 测试中受影响用例迁移（旧 `写入:`/跨帧语法样例更新为函数式）。

## 文档同步

- `docs/contract.md`：§5.3.2 作用域、§5.3.3 块接口、§5.3.5 类型、§5.7.3 块引用、§5.7.4 帧模型重写。
- `docs/specs/M2/M3/M5/M6/M7/M8/M9a` 相应 spec 同步。
- 本文档归档至 `docs/superpowers/specs/2026-09-08-block-function-call-design.md`。
