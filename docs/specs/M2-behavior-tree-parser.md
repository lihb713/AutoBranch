# M2 · 行为树文档解析器 Spec

> 依据契约 `docs/contract.md` §4（行为树文档格式）、§4.1（一文档一树 DSL）、§4.3（复合节点）、§4.4（清晰度校验）、§5.7.3（文档引用机制）、§5.7.4（schema 参数机制）。
>
> **实现状态：已落地**（`webops/parser/` 包，2026-08）。接口细节与实现说明见各节标注。

## 1. 概述

将用户书写的**行为树文档**（yaml/dict，一文档一树）解析为**内部行为树对象**（仅含基础节点），并执行**清晰度校验**。它是书写层与执行层的唯一转换点：复合节点在此展开、文档引用在此解析、变量绑定声明在此提取。**纯逻辑、无外部依赖、最易测试。**

## 2. 功能范围

| 功能 | 说明 | 契约依据 |
|---|---|---|
| 一文档一树解析 | 读取 `tree`/`nodes`/`root`（节点对象池 + 槽位引用），支持跨文档引用 | §4.1 |
| 复合节点展开 | Step/Branch/LoopUntil/IfThenElse/Retry → 基础节点组合 | §4.3 |
| 文档引用解析 | `ref:` 解析（`target: <文档名>` 单段）生成 `RefNode`；参数对齐/跨文档环校验 | §5.7.3 |
| 文档接口声明提取 | 提取文档级 `inputs`/`outputs` 声明供 M3 建立帧 | §5.3/§5.7.4 |
| 配置参数识别 | 识别文档顶层保留键 `timeout`/`retry`/`browser` 覆盖（§5.7.5） | §5.3.4/§5.7.5 |
| 清晰度校验 | 结构/展开/引用/循环上界/变量契约/可定位/验证条件校验 | §4.4 |

**输出**：内部行为树对象——只含 `Action / Condition / Sequence / Selector / Repeat / Finish` 基础节点 + `RefNode`（文档引用调用节点，保留为运行期动态调用），复合节点对引擎不可见。

## 3. 数据依赖

### 3.1 输入
- **行为树文档**：yaml/dict 文本（一文档一树：`tree`/`nodes`/`root`，§4.1）
- **引用文档**：`ref:` 指向的其他文档（跨文档解析时经 `RefResolver` 按文档名加载）

### 3.2 输出
- **内部行为树对象**：`BehaviorTree`，主树（基础节点 + `RefNode`）
- **文档接口声明**：`decl_inputs`（名→类型）/ `decl_outputs`（名列表）
- **主树映射**：`blocks_tree`（文档名 → 该文档主树；运行期 ref 经 resolver 按文档名加载被引文档）
- **全局配置覆盖**：`config`（timeout/retry/browser）
- **校验报告**：清晰度校验通过/失败 + 错误清单（供返回用户修正）

## 4. 单元间依赖

- **依赖**：无（纯逻辑）
- **被依赖**：
  - M7（编排器）— 拿解析后的行为树对象执行
  - M9b（后端）— 保存时校验、执行前校验
  - M3（schema 命名空间）— 解析输出的文档级声明用于建立帧（M7 串联）

## 5. 接口契约

### 5.1 解析入口

```python
class BehaviorTreeParser:
    def parse(self, doc: DocumentSource, ref_resolver: RefResolver) -> ParseResult: ...
```

```python
@dataclass
class ParseResult:
    tree: BehaviorTree                 # 主树（基础节点 + RefNode）
    checks: CheckReport                # 清晰度校验结果
    blocks_tree: dict[str, Node]       # 文档名 → 该文档主树（ref 运行期经 resolver 加载）
    decl_inputs: dict[str, str]        # 文档级入参声明（名 → 类型）
    decl_outputs: list[str]            # 文档级出参名列表
    config: dict[str, object]          # 全局配置覆盖（timeout/retry/browser）
```

**实现说明（已落地）**：

- 模块级便捷入口 `parse(doc, ref_resolver, *, max_expand_depth=64)`。
- `DocumentSource`：`id`（文档名=树名）、`data`（yaml 文本或 dict）、可选 `path`。
- `RefResolver`：`resolve(doc_id) -> DocumentSource`（**单参数**），文档缺失抛 `RefNotFoundError(doc_id)`；提供内存实现 `MappingResolver`（测试/简单场景）。
- 一文档一树解析入口 `webops/parser/onedoc.py::parse_document`：校验 `tree`（须=文档名，否则 `structure.name_mismatch`）、`nodes`/`root`（`root` 须指向 `type: Root` 节点）、文档级 `inputs`/`outputs`、顶层配置保留键；从 `root` 沿各节点的**语义槽位字段**（`body`/`actions`/`action`/`then`/`else`/`branches`）构建主树，未被任何槽位字段引用的节点为游离树；ref 参数对齐与跨文档环校验（需传入 resolver）。
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
@dataclass
class RefNode(Node):
    ref_target: str                      # 目标文档名（单段）
    args: tuple[tuple[str, str], ...]    # (实参名, 实参表达式)；实参 = 父帧裸路径 裸变量名 或字面量
    returns: tuple[tuple[str, str], ...] # (本树接收名, 类型)；被引文档 SUCCESS 后回收写父帧
```

**实现说明（已落地）**：

- 节点均为 `frozen` dataclass，保证确定性输出；组合结构使用 `tuple`（可哈希、比较稳定）。
- `Node` 基类仅含 `loc: Loc | None`（文档位置，路径式定位）。运行期帧由 `RefNode` 动态调用（M7 `_tick_ref`）维护，节点不携带静态帧标识。
- `RefNode`：文档引用调用节点（`target` 为单段文档名），保留为运行期动态调用，**不内联展开**；`args`/`returns` 携带参数声明（§5.7.3）。
- `ConditionNode` 扩展可选字段（超出 §5.2 的 description-only，供谓词结构校验与 M6 执行）：`target`（谓词指向对象）、`predicate`（比较谓词）。
- `BranchSpec(condition: ConditionNode | None, child: Node)`：`condition=None` 表示 otherwise 兜底分支。
- `BehaviorTree(name: str, root: Node)`：树名（=文档名） + 基础节点根。
- 文档格式（一文档一树，§4.1）：`tree: <名>`（须=文档名，否则 `structure.name_mismatch`）+ 可选 `inputs`/`outputs` + 可选保留配置键（`timeout`/`retry`/`browser`）+ `nodes`（节点对象池，每节点 `{id, type, name, ...标量字段, <语义槽位字段>}`；槽位字段按类型：`Root.body` / `Sequence.actions` / `Step.action` / `IfThenElse.then`+`else` / `Branch.action`+`branches[].action` / `Retry.body` / `LoopUntil.action`，值=子树根 id）+ `root: <id>`（须指向 `type: Root` 节点）。节点类型 `Action/Root/Step/Sequence/IfThenElse/Branch/Retry/LoopUntil/ref`；`Action` 为真正叶子（`description` 操作描述），`Step` 的 `action` 槽位挂操作子树、`expect` 为验证条件字段。

### 5.3 复合节点展开规则（§4.3）

| 复合节点 | 展开结果 |
|---|---|
| Step | `Sequence(action 槽位子树 + Condition(expect))` |
| Branch | `Sequence(action 槽位子树 + Selector(branches 各 action 子树))`（顺序检查 when，第一个命中生效，无匹配走 otherwise） |
| LoopUntil | `Repeat(mode=loop_until, until=条件, max=上限, body=action 槽位子树)` |
| Retry | `Repeat(mode=retry, max=上限, body=body 槽位子树)` |
| IfThenElse | `Selector(if→then 槽位子树, else→else 槽位子树)` |

**实现说明（已落地）**：展开规则集中于单一映射表 `EXPANSION_RULES`（`webops/parser/expand.py`），表驱动测试直接覆盖五类复合节点多组样例；复合嵌套深度由计数器防护（`expand.depth_exceeded`）。ref 的跨文档环与参数对齐在 onedoc 解析期校验（`ref.cross_doc_cycle` / `ref.args_mismatch` / `ref.returns_mismatch` / `ref.name_conflict`）。

### 5.4 清晰度校验规则（§4.4）

校验项：结构合法、展开后合法、文档引用存在、循环有上界、变量契约一致（引用在可见作用域内）、动作可定位（有 CSS 或有自然语言）、每步有验证条件、条件谓词结构可校验。

**实现说明（已落地）**：校验按类别独立成规则，汇总为 `CheckReport`（`webops/parser/checks.py` 汇总 + `expand.py` 展开期规则）。错误项 `CheckIssue(code, message, loc, rule)` 逐条可读、可定位、指明违反规则：

| 错误码前缀 | 规则名 | 典型错误码 |
|---|---|---|
| `structure` | 结构合法性 | `structure.name_mismatch` / `missing_tree` / `missing_nodes` / `invalid_root` / `invalid_decl` / `unknown_node` / `invalid_node` / `orphan_slot` / `duplicate_reference` / `cycle` / `missing_field` / `invalid_value` |
| `expand` | 展开后合法性 | `expand.residual_composite` / `depth_exceeded` |
| `ref` | 文档引用 | `ref.bad_syntax` / `missing_doc` / `cross_doc_cycle` / `args_mismatch` / `returns_mismatch` / `name_conflict` |
| `repeat` | 循环上界 | `repeat.max_missing` / `max_not_int` |
| `scope` | 变量契约 | `scope.out_of_scope` / `get_undeclared` |
| `locatable` | 可定位性 | `locatable.not_locatable` / `no_description` |
| `verify` | 验证条件 | `verify.missing_condition` |
| `predicate` | 谓词可校验 | `predicate.empty_condition` |

**文档格式与变量契约落地细节**：

- 统一槽位模型下，分支目标不支持裸字符串 = `ref: <文档名>` 简写（旧 §4.3.2「分支目标 = 文档引用」写法已废除）——`Branch.branches[].action` 与 `otherwise` 均为槽位字段，值为子树根 id；跨文档复用由分支子树里的 `ref` 节点承担。
- 配置参数覆盖在文档顶层识别（`timeout`/`retry`/`browser` 标量），未声明不要求用户书写（§4.2/§5.7.5）。
- 变量作用域校验（§5.3.2）：语法 `[[get:变量]]`（读取引用）/`[[set:类型:变量]]`（写入声明）——**裸变量名**（作用于当前文档执行帧），无层级；旧式 `裸变量名` 前缀为兼容写法。跨帧传参经 ref args/returns。**get 已定义校验**：`[[get:x]]` 的 x 必须是本文档 inputs 声明、文档内 `[[set:...]]` 目标或 ref returns 目标，否则 `scope.get_undeclared`（output 声明不构成 get 源）。`ActionNode.set_targets` 记录动作的 `[[set:...]]` 可写集（裸变量名）；`ActionNode.set_decls` 记录类型标注 `[[set:page_ref:页面A]]`（存页签引用 PageRef）与 `[[set:str:url]]`（存文本），type ∈ TYPE_REGISTRY token（str/int/float/bool/page_ref），type 为空串时按动作推断；`[[get:...]]` 运行时由引擎替换（M6 职责），M2 仅作用域与已定义校验。
- 引用处参数契约（§5.7.3）：被引文档声明的 `inputs` 须由 ref `args` 按数量/类型对应，`outputs` 由 `returns` 按数量对应；不一致 → `ref.args_mismatch` / `ref.returns_mismatch` / `ref.name_conflict`。

## 6. 验收标准

- [x] 合法一文档一树文档 → 解析为主树（纯基础节点，复合节点全部展开），游离节点保留为游离树
- [x] 复合节点展开结果与 §4.3 精确语义一致（Step/Branch/LoopUntil/Retry/IfThenElse）
- [x] 文档引用解析正确（`target: <文档名>` 单段、跨文档整树引用）
- [x] 校验能发现：结构非法（树名不符/单根/孤儿槽位/重复引用/成环）、引用不存在、参数不对齐、循环无上界、变量越作用域、动作不可定位、缺验证条件
- [x] 校验失败返回可读的错误清单
- [x] 纯函数测试：同一输入文档 → 确定性输出

## 7. 测试策略

- **纯函数测试**：输入文档 yaml → 断言输出主树结构与文档级声明
- **复合节点展开表驱动测试**：每个复合节点的多组样例 → 期望展开结构
- **校验用例矩阵**：对 §4.4 每类违规构造反例，验证正确报错
- **跨文档引用测试**：多文档 fixture，验证按文档名解析与参数对齐
- **独立性**：不依赖 LLM、不依赖浏览器，可单独运行全部测试

**实现说明（已落地）**：`tests/test_parser_onedoc.py` + `tests/test_parser_onedoc_integration.py`（多文档 fixture）；覆盖一文档一树解析、槽位/游离树/单根/无环/重复引用校验、ref 参数对齐与跨文档环、配置覆盖与变量绑定，并断言 `blocks_tree`（文档名 → 主树）与 `RefNode`（ref 保留为调用节点，不内联）。

## 8. 依赖与运行说明（实现补充）

- 模块为纯逻辑，无外部运行时依赖（不依赖 LLM / 浏览器）。
- yaml 文本入口优先使用 PyYAML（**已列入项目硬依赖，`pyproject.toml` `pyyaml>=6.0`**）；标准库内置的 **YAML 子集解析器**（`webops/parser/yamlio.py`）仅作 PyYAML 缺失时的兜底，覆盖行为树文档常见结构（缩进映射/序列、流式 `{k: v}`/`[a, b]`、引号、注释、块标量）。完整 YAML 规范（别名/锚点/多文档流）需 PyYAML。
- 解析器测试在 `webops` conda 环境内随 `pytest` 全量运行。