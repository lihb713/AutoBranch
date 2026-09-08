# M2 · 行为树文档解析器 Spec

> 依据契约 `docs/contract.md` §4（行为树文档格式）、§4.3（复合节点）、§4.4（清晰度校验）、§5.7.3（块引用机制）、§5.7.4（schema 参数机制）。
>
> **实现状态：已落地**（`webops/parser/` 包，2026-08）。接口细节与实现说明见各节标注。

## 1. 概述

将用户书写的**行为树文档**（yaml/dict）解析为**内部行为树对象**（仅含基础节点），并执行**清晰度校验**。它是书写层与执行层的唯一转换点：复合节点在此展开、块引用在此解析、变量绑定声明在此提取。**纯逻辑、无外部依赖、最易测试。**

## 2. 功能范围

| 功能 | 说明 | 契约依据 |
|---|---|---|
| yaml/dict 解析 | 读取行为树文档（支持多文档/跨文档引用） | §4.1 |
| 复合节点展开 | Step/Branch/LoopUntil/IfThenElse/Retry → 基础节点组合 | §4.3 |
| 块引用解析 | `ref:` 解析（this/文档名/块名），跨文档引用解析 | §5.7.3 |
| schema 绑定声明提取 | 提取块接口声明（输入/输出）供 M3 建立命名空间 | §5.3/§5.7.4 |
| 配置参数声明识别 | 识别块 schema 下的配置参数覆盖（§5.7.5） | §5.3.4/§5.7.5 |
| 清晰度校验 | 结构/展开/引用/循环上界/变量契约/可定位/验证条件校验 | §4.4 |

**输出**：内部行为树对象——只含 `Action / Condition / Sequence / Selector / Repeat / Finish` 基础节点，复合节点对引擎不可见。

## 3. 数据依赖

### 3.1 输入
- **行为树文档**：yaml/dict 文本（操作块定义 + 根流程，§4.1）
- **引用文档**：`ref:` 指向的其他文档（跨文档解析时加载）

### 3.2 输出
- **内部行为树对象**：`BehaviorTree`，节点树（基础节点）
- **块声明表**：每个命名块的输入/输出/配置参数声明
- **校验报告**：清晰度校验通过/失败 + 错误清单（供返回用户修正）

## 4. 单元间依赖

- **依赖**：无（纯逻辑）
- **被依赖**：
  - M7（编排器）— 拿解析后的行为树对象执行
  - M9b（后端）— 保存时校验、执行前校验
  - M3（schema 命名空间）— 解析输出的块声明用于建立命名空间（M7 串联）

## 5. 接口契约

### 5.1 解析入口

```python
class BehaviorTreeParser:
    def parse(self, doc: DocumentSource, ref_resolver: RefResolver) -> ParseResult: ...
```

```python
@dataclass
class ParseResult:
    tree: BehaviorTree            # 内部行为树（仅基础节点）
    blocks: dict[str, BlockDecl]  # 命名块声明（输入/输出/配置参数）
    checks: CheckReport           # 清晰度校验结果
```

**实现说明（已落地）**：

- 模块级便捷入口 `parse(doc, ref_resolver, *, max_expand_depth=64)`。
- `DocumentSource`：`id`（文档名=根块名）、`data`（yaml 文本或 dict）、可选 `path`。
- `RefResolver`：`resolve(doc_id, block_name=None) -> DocumentSource`，文档缺失抛 `RefNotFoundError`；提供内存实现 `MappingResolver`（测试/简单场景）。
- `ParseResult` 扩展字段（超出 §5.1 三字段，供命名空间/绑定校验与下游使用）：
  `bindings: tuple[ParamBinding]`（引用处 `写入` 绑定记录）、`frames: tuple[FrameInfo]`（schema 命名空间帧层级，§5.7.4）。
- 非法输入（非 yaml/dict、非顶层映射）抛 `InvalidDocumentError`，不产生部分结果；结构/语义违规以 `checks` 错误清单返回。

### 5.2 基础节点模型

```python
@dataclass
class Node: ...
@dataclass
class ActionNode(Node):      # 自然语言描述 + 可选 CSS 提示
    description: str
    css_hint: str | None
@dataclass
class ConditionNode(Node):
    description: str
@dataclass
class SequenceNode(Node):
    children: list[Node]
@dataclass
class SelectorNode(Node):
    branches: list[BranchSpec]      # 条件 → 子节点
@dataclass
class RepeatNode(Node):
    body: Node
    mode: Literal["loop_until", "retry"]
    until: ConditionNode | None    # LoopUntil 的 until 条件
    max: int                       # 循环上界（安全闸）
@dataclass
class FinishNode(Node): ...
```

**实现说明（已落地）**：

- 节点均为 `frozen` dataclass，保证确定性输出；组合结构使用 `tuple`（可哈希、比较稳定）。
- `Node` 基类含 `loc: Loc | None`（文档位置，路径式定位）与 `frame: str`（所属 schema 命名空间帧路径，§5.7.4，供 M7 执行定位）。
- `ConditionNode` 扩展可选字段（超出 §5.2 的 description-only，供谓词结构校验与 M6 执行）：`target`（谓词指向对象）、`predicate`（比较谓词）。
- `BranchSpec(condition: ConditionNode | None, child: Node)`：`condition=None` 表示 otherwise 兜底分支。
- `BehaviorTree(name: str, root: Node)`：根块名 + 基础节点根。
- 文档格式明确化（§4.1 图示的落地写法，见实现）：
  - 写法 A/B：顶层 `操作块 <块名>:` 键（可多个），根块 = 名字匹配文档名的块，无匹配取第一个；其余为命名块（供 `this/块名` 引用）。
  - 写法 C（极简）：整个 dict 即根块行为树（根块名 = 文档名）。
  - 块体 = `输入`/`输出` 声明 + 配置参数覆盖（`timeout`/`retry`/`browser` 标量）+ 恰好一个行为树节点键。

### 5.3 复合节点展开规则（§4.3）

| 复合节点 | 展开结果 |
|---|---|
| Step | `Sequence(Action + Condition)` |
| Branch | `Action + Selector`（顺序检查 when，第一个命中生效，无匹配走 otherwise） |
| LoopUntil | `Repeat(mode=loop_until, until=条件, max=上限)` |
| Retry | `Repeat(mode=retry, max=上限)` |
| IfThenElse | `Selector(if→then, else→else)` |

**实现说明（已落地）**：展开规则集中于单一映射表 `EXPANSION_RULES`（`webops/parser/expand.py`），表驱动测试直接覆盖五类复合节点多组样例；展开深度与引用嵌套分别由复合嵌套计数器与调用栈（`ctx.stack`）防护，超限按校验失败处理（`expand.depth_exceeded` / `ref.recursion_depth`）。

### 5.4 清晰度校验规则（§4.4）

校验项：结构合法、展开后合法、块引用存在、循环有上界、变量契约一致（引用在可见作用域内）、动作可定位（有 CSS 或有自然语言）、每步有验证条件、条件谓词结构可校验。

**实现说明（已落地）**：校验按类别独立成规则，汇总为 `CheckReport`（`webops/parser/checks.py` 汇总 + `expand.py` 展开期规则）。错误项 `CheckIssue(code, message, loc, rule)` 逐条可读、可定位、指明违反规则：

| 错误码前缀 | 规则名 | 典型错误码 |
|---|---|---|
| `structure` | 结构合法性 | `structure.unknown_node` / `invalid_flow` / `missing_field` / `invalid_node` |
| `expand` | 展开后合法性 | `expand.residual_composite` / `depth_exceeded` |
| `ref` | 块引用存在 | `ref.missing_doc` / `missing_block` / `cycle` / `input_not_bound` / `binding_target` / `binding_not_input` |
| `repeat` | 循环上界 | `repeat.max_missing` / `max_not_int` |
| `scope` | 变量契约 | `scope.out_of_scope` |
| `locatable` | 可定位性 | `locatable.not_locatable` |
| `verify` | 验证条件 | `verify.missing_condition` |
| `predicate` | 谓词可校验 | `predicate.empty_condition` |

**文档格式与变量契约落地细节**：

- 分支目标支持裸字符串 = `ref: this/块名` 简写（对齐 §4.3.2「分支目标 = 块引用」）。
- 配置参数覆盖仅在块 schema 级识别（`timeout`/`retry`/`browser` 标量），未声明不要求用户书写（§4.2/§5.7.5）。
- 变量作用域校验（§5.3.2）：新语法 `{{get:this/变量}}`（读取引用）/`{{set:this/变量}}`（写入声明）——`this/变量`（自身）、`this/直接子块/变量`（直接子块）合法；三 segment 及以上（孙子/更深）或指向非直接子块 → `scope.out_of_scope`。`ActionNode.set_targets` 记录动作的 `{{set:...}}` 可写集；`ActionNode.set_decls` 记录类型标注 `{{set:page_ref:this/页面A}}`（存页签引用 PageRef）与 `{{set:str:this/url}}`（存文本），type ∈ TYPE_REGISTRY token（str/int/float/bool/page_ref），type 为空串时按动作推断；`{{get:...}}` 运行时由引擎替换（M6 职责），M2 仅作用域校验。兼容旧 `$this/` 绑定路径（ref `写入:` 机制）。
- 引用处绑定契约（§5.7.3）：被引用块声明输入必须在 ref 处用 `写入` 全部绑定，绑定目标须为被引用块声明输入，否则校验失败。

## 6. 验收标准

- [x] 合法文档 → 解析为纯基础节点行为树，复合节点全部展开
- [x] 复合节点展开结果与 §4.3 精确语义一致（Step/Branch/LoopUntil/Retry/IfThenElse）
- [x] 块引用解析正确（this/文档名/块名、跨文档整树引用）
- [x] 校验能发现：结构非法、引用不存在、循环无上界、变量越作用域、动作不可定位、缺验证条件
- [x] 校验失败返回可读的错误清单
- [x] 纯函数测试：同一输入文档 → 确定性输出

## 7. 测试策略

- **纯函数测试**：输入文档 yaml → 断言输出行为树结构与块声明
- **复合节点展开表驱动测试**：每个复合节点的多组样例 → 期望展开结构
- **校验用例矩阵**：对 §4.4 每类违规构造反例，验证正确报错
- **跨文档引用测试**：多文档 fixture，验证解析与引用解析
- **独立性**：不依赖 LLM、不依赖浏览器，可单独运行全部测试

**实现说明（已落地）**：`tests/test_parser_{models,document,expand,refs,checks,integration}.py` + `tests/parser_fixtures.py` 共 84 项普通 pytest 测试（无 integration 标记）；多文档 fixture 对齐 §5.7.6 完整示例（登录/导出/主流程），覆盖跨文档引用、配置覆盖、变量绑定与命名空间帧。

## 8. 依赖与运行说明（实现补充）

- 模块为纯逻辑，无外部运行时依赖（不依赖 LLM / 浏览器）。
- yaml 文本入口优先使用 PyYAML；当前 `webops` conda 环境未安装 PyYAML，由标准库内置的 **YAML 子集解析器**（`webops/parser/yamlio.py`）兜底，覆盖行为树文档常见结构（缩进映射/序列、流式 `{k: v}`/`[a, b]`、引号、注释、块标量）。完整 YAML 规范（别名/锚点/多文档流）需安装 PyYAML。
- 解析器测试在 `webops` conda 环境内随 `pytest` 全量运行。