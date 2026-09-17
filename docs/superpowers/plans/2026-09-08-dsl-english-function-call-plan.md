# Plan ②：DSL 英文化 + [[ ]] 变量语法 + 引用块函数式传参静态校验

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把行为树 DSL 语法英文化（`block`/`inputs`/`outputs`/`args`/`returns`），变量占位符 `{{ }}` 改为 `[[ ]]`，ref 传参改为显式函数式调用（args 传实参 / returns 接收返回值），并在解析期完成全部静态校验（args⊆inputs、returns⊆outputs、inputs 全必填、output 全赋值、类型 token 已注册、作用域单段）。

**Architecture:** 改动集中在 M2 parser（document.py 语法解析、expand.py 静态校验、models.py 数据结构）+ 最低限度的运行时同步（leaf_agent executor 的 get 替换正则、prompts 示例）使现有"静态展开 + node.frame"运行机制在新语法下不 break。**不实现动态调用执行器/帧实例化/帧销毁**（那属 Plan ③）。typed inputs 顺带注入 `context.py:66` schema_decl，使 M3 `frame.inputs` 携带真实声明类型（运行期 `_declared_type` 随之返回真实类型——这是期望行为，Plan ③ 统一验收）。

**Tech Stack:** Python 3.11, dataclass, pytest, TypeScript (前端 model.ts / e2e)。

**Spec:** `docs/superpowers/specs/2026-09-08-block-function-call-design.md`（§1 完整 DSL、§2 类型、§4 两阶段校验、§5 作用域）

## Global Constraints

- 全程中文对话与文档，但 DSL 关键字/类型 token 用英文。
- conda 环境 `autobranch`：`conda run -n autobranch --no-capture-output python -m pytest ...`。前端命令在 `autobranch/frontend` 用 `npm.cmd ...`。
- 类型 token 唯一来源 `TYPE_REGISTRY` 键：`str/int/float/bool/page_ref`（Plan ① 已落地）。
- 新 DSL 关键字（唯一拼写）：块前缀 `block `；声明键 `inputs`/`outputs`；ref 子键 `args`/`returns`。**废除**：`操作块 `、`输入`/`输出`、`写入`、`$this/块/名` 三段路径、`{{ }}` 变量分隔、旧 `$` 前缀。
- 变量语法（唯一形态）：读取 `[[get:this/<名>]]`；写入 `[[set:<类型>:this/<名>]]`（类型必填——设计 §变量语法形态；**但注意 Plan ① 阶段 set 类型是可选**，本 plan 是否强制必填见 Task 决策，默认保持可选、空类型按动作推断，强制必填属 Plan ③/④ 语法收紧）。
- args/returns 值：裸路径 `this/<名>` 或字面量（无 get/set 标注）。
- `inputs` dict 形态 `{名: 类型}`；`outputs` 保持纯名字（串/列表）。
- 静态校验在解析期完成；运行期执行器（traverser/engine）除 get 替换正则与 schema_decl 类型注入外**不改**。
- 前端 tree-editor `model.ts` 硬编码 `操作块 ` 前缀须同步；前端 E2E 与 server 测试样例须迁移。

---

### Task 1: parser 模型与语法解析改造（document.py + models.py）

**Files:**
- Modify: `autobranch/parser/models.py:178-194`（BlockDecl.inputs 类型化）、`autobranch/parser/document.py:46-51`（常量）、`:137-179`（parse_structure）、`:182-274`（_parse_block_body/_parse_decl_list）、`:81-107`（IRNode 加 args/returns）、`:314-353`（_parse_node_entry）、`:356-413`（_parse_ref）
- Test: `tests/test_parser_document.py`、`tests/test_parser_models.py`、`tests/test_parser_refs.py`（本任务迁移这三个文件的语法样例）

**Interfaces:**
- Consumes: `TYPE_REGISTRY` 键（str/int/float/bool/page_ref）
- Produces:
  - `BLOCK_PREFIX = "block "`；`DECL_KEYS = frozenset({"inputs", "outputs"})`
  - `BlockDecl.inputs: tuple[tuple[str, str], ...]`（名,类型）；`outputs: tuple[str, ...]`（不变）
  - IRNode 新增 `args: tuple[tuple[str, str], ...]`（形参名,实参表达式）、`returns: tuple[tuple[str, str], ...]`（输出名,父块目标变量），在 `bindings` 与 `raw` 之间
  - `_parse_decl_list` 支持 dict（inputs `{名: 类型}`，值须 ∈ TYPE_REGISTRY 键否则报 `structure.invalid_decl`），返回 `tuple[tuple[str,str],...]`；outputs 保持名字串/列表
  - ref 子键 `args`/`returns`（值 dict）；`写入` 键废除（出现报错）

- [ ] **Step 1: 写失败测试（迁移 tests/test_parser_document.py / test_parser_models.py / test_parser_refs.py 语法样例）**

把这三个测试文件里所有中文 DSL 样例迁移为新语法。代表（tests/parser_fixtures.py 也同步，见 Task 5 但此处先改内联样例）：
- `操作块 登录:` → `block 登录:`
- `输入: $username, $password` → `inputs: {username: str, password: str}`
- `输出: $login_success` → `outputs: login_success`
- `ref: this/登录` + `写入: {…}` → `ref: this/登录` + `args: {username: this/账号, ...}` + `returns: {...}`
- `{{get:...}}`/`{{set:...}}` → `[[get:...]]`/`[[set:...]]`（Task 2 的正则才接受；此处测试断言先写新语法，Task 2 实现正则）
- `$this/块/名` → 单段 `this/名`

Run: `conda run -n autobranch --no-capture-output python -m pytest tests/test_parser_document.py tests/test_parser_models.py tests/test_parser_refs.py -q`
Expected: FAIL（语法未实现）

- [ ] **Step 2: 改 models.py BlockDecl 与 IRNode**

`autobranch/parser/models.py`：
```python
@dataclass(frozen=True)
class BlockDecl:
    name: str
    doc_id: str
    inputs: tuple[tuple[str, str], ...] = ()   # (变量名, 类型 token)；输出保持 tuple[str, ...]
    outputs: tuple[str, ...] = ()
    config_overrides: tuple[ConfigOverride, ...] = ()
    loc: Loc | None = None
```
IRNode（document.py 91-107）在 `bindings` 后加：
```python
    args: tuple[tuple[str, str], ...] = ()
    returns: tuple[tuple[str, str], ...] = ()
```

- [ ] **Step 3: 改 document.py 常量与声明解析**

- `BLOCK_PREFIX = "block "`；`DECL_KEYS = frozenset({"inputs", "outputs"})`；`CONFIG_PARAMS` 不变。
- `parse_structure`（143-144）`key.startswith(BLOCK_PREFIX)` 逻辑不变（前缀值变了即生效）；152 行错误消息"顶层混用「操作块」定义"改为"顶层混用 block 定义"。
- `_parse_block_body`（194-195）：`inputs = _parse_decl_list(body.get("inputs"), ...)`、`outputs = _parse_decl_list(body.get("outputs"), ...)`。
- `_parse_decl_list`（252-274）重写为：
```python
def _parse_decl_list(
    value: object, doc_id: str, name: str, decl_name: str, issues: list[CheckIssue]
) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if decl_name == "inputs" and isinstance(value, dict):
        result: list[tuple[str, str]] = []
        for k, v in value.items():
            if not isinstance(k, str) or not isinstance(v, str):
                issues.append(make_issue("structure", "invalid_decl",
                    f"块 '{name}' 的 inputs 必须是 变量名: 类型 的映射（位于 {_path(doc_id, name)}）", _loc(doc_id, name)))
                continue
            var = k.strip().lstrip("$")
            typ = v.strip()
            if not var:
                continue
            if typ and typ not in TYPE_REGISTRY:
                issues.append(make_issue("structure", "invalid_decl",
                    f"块 '{name}' 的输入 '{var}' 类型 '{typ}' 未登记（支持: {sorted(TYPE_REGISTRY)}）", _loc(doc_id, name)))
                continue
            result.append((var, typ))
        return tuple(result)
    # outputs（或 inputs 非 dict 形态）：名字串/列表，产出 (名, "")
    result: list[tuple[str, str]] = []
    if isinstance(value, str):
        items = [s.strip().lstrip("$") for s in value.split(",")]
    elif isinstance(value, list):
        items = [str(i).strip().lstrip("$") for i in value]
    else:
        issues.append(make_issue("structure", "invalid_decl",
            f"块 '{name}' 的 {decl_name} 声明必须是字符串/列表（或 inputs 用映射）（位于 {_path(doc_id, name)}）", _loc(doc_id, name)))
        return ()
    for s in items:
        if s:
            result.append((s, ""))
    return tuple(result)
```
> 说明：inputs 的 dict 形态产出 `(名, 类型)`；outputs 及非 dict 的 inputs 产出 `(名, "")`（空类型=未声明，与 set_decls 无类型约定一致）。`from autobranch.schema.types import TYPE_REGISTRY` 在 document.py 顶部引入。
> 调用点 194/195 处 outputs 变量仍是 `tuple[tuple[str,str],...]`，BlockDecl 构造（190/225-232/239-246）自动适配新字段类型。

- [ ] **Step 4: 改 ref 解析（args/returns，废除写入）**

`_parse_node_entry`（330-343）：ref 的 extra 白名单从 `["写入"]` 改为 `["args", "returns"]`；`_parse_ref` 签名改 `(doc_id, path, target, args=None, returns=None, issues=None)`：
```python
def _parse_ref(doc_id, path, target, args=None, returns=None, issues=None):
    # ...(target 校验同现状)...
    args_pairs = _parse_kv(args, "args", doc_id, path, issues)
    returns_pairs = _parse_kv(returns, "returns", doc_id, path, issues)
    return IRNode(kind="ref", ref_target=target, args=tuple(args_pairs),
                  returns=tuple(returns_pairs), loc=loc)
```
新增辅助 `_parse_kv(value, key_name, doc_id, path, issues) -> list[tuple[str,str]]`：值必须 dict，键值须标量，返回 `(k.strip(), str(v))`；非法报 `structure.invalid_binding`。bindings 字段本任务保留但不再由 `写入` 填充（Task 3 静态校验改走 args/returns；bindings/ParamBinding 在 Plan ③ 移除，本 plan 先不删以免破坏 FrameInfo 等）。

- [ ] **Step 5: 运行确认通过**

Run: `conda run -n autobranch --no-capture-output python -m pytest tests/test_parser_document.py tests/test_parser_models.py tests/test_parser_refs.py -q`
Expected: PASS（注意：task 里仍含 `写入`/`{{ }}` 的旧样例此时会失败——见 Step 6 说明）

- [ ] **Step 6: 处理仍失败的内联旧语法**

其余测试文件（test_parser_expand/checks/integration/vars、test_parser_fixtures、server 等）的旧语法样例**暂不迁移**，此时会因新前缀/键而报错。本任务只保证上述 3 个文件绿。Run: `conda run -n autobranch --no-capture-output python -m pytest tests/test_parser_document.py tests/test_parser_models.py tests/test_parser_refs.py -q` 确认这三个绿，其余红是 Task 5 迁移范围。

- [ ] **Step 7: Commit**

```bash
git add autobranch/parser/models.py autobranch/parser/document.py tests/test_parser_document.py tests/test_parser_models.py tests/test_parser_refs.py
git commit -m "feat(parser): english DSL syntax (block/inputs/outputs/args/returns)"
```

---

### Task 2: [[ ]] 变量语法 + 最低运行时同步

**Files:**
- Modify: `autobranch/parser/expand.py:40-47`（正则）、`autobranch/leaf_agent/executor.py:69`（_GET_TMPL）、`autobranch/leaf_agent/prompts.py`（示例）、`autobranch/engine/tools.py`（示例）
- Test: `tests/test_parser_vars.py`、`tests/leaf_agent/test_get_replace.py`

**Interfaces:**
- Consumes: Task 1 的 IRNode.args/returns（本任务不依赖，独立）
- Produces:
  - `_GET_TMPL = re.compile(r"\[\[\s*get:\s*this/([^\[\]]+?)\s*\]\]")`
  - `_SET_TMPL = re.compile(r"\[\[\s*set:(?:(str|int|float|bool|page_ref):)?\s*((?:this/)?[^\[\]:]+?)\s*\]\]")`
  - executor `_GET_TMPL` 同步（M6 运行期 get 替换）

- [ ] **Step 1: 写失败测试**

迁移 `tests/test_parser_vars.py`（13 用例）与 `tests/leaf_agent/test_get_replace.py` 的占位符：`{{get:this/x}}`→`[[get:this/x]]`、`{{set:type:this/x}}`→`[[set:type:this/x]]`。断言值不变。

Run: `conda run -n autobranch --no-capture-output python -m pytest tests/test_parser_vars.py tests/leaf_agent/test_get_replace.py -q`
Expected: FAIL

- [ ] **Step 2: 改 expand.py 正则**

按 4d 建议正则替换 `_GET_TMPL`/`_SET_TMPL`（expand.py 40-45）。`_iter_schema_paths`（81-92）的 sub 逻辑不变。

- [ ] **Step 3: 改 executor.py 正则**

`autobranch/leaf_agent/executor.py:69` 的 `_GET_TMPL` 同步为 `\[\[...\]\]` 版。

- [ ] **Step 4: 同步 prompts/tools 示例**

`prompts.py` build_user_message 的 set 示例文案、`tools.py` open/get_url 描述里的 `{{set:page_ref:...}}`/`{{set:str:...}}` 全部改 `[[set:page_ref:...]]`/`[[set:str:...]]`。

- [ ] **Step 5: 运行确认通过**

Run: `conda run -n autobranch --no-capture-output python -m pytest tests/test_parser_vars.py tests/leaf_agent/test_get_replace.py tests/leaf_agent/test_prompts.py tests/leaf_agent/test_regression.py tests/engine/test_engine.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add autobranch/parser/expand.py autobranch/leaf_agent/executor.py autobranch/leaf_agent/prompts.py autobranch/engine/tools.py tests/
git commit -m "feat(dsl): [[ ]] variable delimiters with runtime get sync"
```

---

### Task 3: 静态校验（args/returns/inputs 必填/output 全赋值/单段作用域）

**Files:**
- Modify: `autobranch/parser/expand.py`（_expand_ref 校验、新增 output 全赋值校验、_check_schema_path 单段化）、`autobranch/parser/models.py:19-28`（RULE_BY_PREFIX 加新错误码前缀）
- Test: `tests/test_parser_expand.py`、`tests/test_parser_checks.py`（新校验用例）

**Interfaces:**
- Consumes: Task 1 的 `BlockDecl.inputs: tuple[tuple[str,str],...]`、IRNode.args/returns；`TYPE_REGISTRY` 键
- Produces:
  - 校验错误码：`ref.args_not_input`（args 键 ⊆ inputs）、`ref.input_not_bound`（inputs 全必填，沿用）、`ref.returns_not_output`（returns 键 ⊆ outputs）、`ref.output_not_set`（outputs 全赋值）、`scope.out_of_scope`（单段作用域，沿用）
  - `_check_schema_path` 收敛为仅 `this/<名>` 单段合法（直接子块段不再合法——函数式传参后无跨帧读写）

- [ ] **Step 1: 写失败测试（tests/test_parser_expand.py 新增）**

```python
def test_args_must_match_inputs():
    doc = {"block 登录": {"inputs": {"username": "str"}, "outputs": "", "Sequence": [{"Step": {"action": "x"}}]},
           "block 主": {"Sequence": [{"ref": "this/登录", "args": {"username": "this/u", "wrong": "this/v"}}]}}
    issues = parse_doc(doc)   # 用测试现有 helper（参照 test_parser_refs 的解析入口）
    assert any(i.code == "ref.args_not_input" for i in issues)

def test_outputs_must_be_assigned():
    doc = {"block 登录": {"inputs": {}, "outputs": "p1, p2", "Sequence": [{"Step": {"action": "提取 [[set:str:this/p1]]"}}]}}
    issues = parse_doc(doc)
    assert any(i.code == "ref.output_not_set" for i in issues)   # p2 未赋值
```
（test helper：用现有 `tests/parser_fixtures.py`/conftest 的解析入口，参照现有测试写法。）

Run: `conda run -n autobranch --no-capture-output python -m pytest tests/test_parser_expand.py -q`
Expected: FAIL（校验未实现）

- [ ] **Step 2: 改 _expand_ref 校验逻辑**

- `t_inputs = t_decl.inputs`（现在是 `tuple[tuple[str,str],...]`），名字集合 `{n for n,_ in t_inputs}`；类型字典 `{n: t for n,t in t_inputs}`。
- args 校验：`for arg_name, expr in node.args:` → `if arg_name not in input_names: 报 ref.args_not_input`；否则 `bound_vars.add(arg_name)`；对 `expr` 做 `_scope_check_texts`（作用域单段）。
- inputs 全必填：`missing = [n for n,_ in t_inputs if n not in bound_vars]` → `ref.input_not_bound`。
- returns 校验：`for out_name, target in node.returns:` → `if out_name not in t_outputs: 报 ref.returns_not_output`；`target` 做 `_check_schema_path`（须 `this/<名>` 单段）。
- 废除 `写入:` 的 ParamBinding 收集（本任务起 args/returns 取代；bindings 相关删除或保留空——见 Task 1 决策，Plan ③ 移除）。

- [ ] **Step 3: output 全赋值校验（expand_document 或 _expand_ir 处）**

在 `expand_document` 展开后，对**每个块**（根块 + 本块内 ref 引用的命名块？——见语义决策）检查：块声明的每个 output 名，其**块体树内**（不含 ref 子块内部，ref 子块输出经 returns 是另一帧）存在赋值点 = 叶子 `[[set:...:this/<名>]]`（set_decls）或**本块 ref 的 returns 目标** `returns: {..., <名>: this/...}` 的目标名含该 output。实现一个轻量走查（参照 `_collect_ref_blocks` expand.py 188-209 的结构：遍历 children/branches/action/condition/until/body；遇 ref 检查其 returns 目标并**不深入**被引用块）。缺失 → `ref.output_not_set`。
> 语义决策（写进代码注释）：输出赋值点 = 块体自身帧内的 set 或本块 ref 的 returns 目标；ref 子块内部如何产出它的输出由该子块自己校验（递归性质，因每个块都被检查）。为控制范围，本任务对**文档内所有命名块**（含 ref 引用的跨文档块，经 `ctx.ir_by_block`/doc_cache 取树）执行该检查。
> 若某块被 ref 多次，仍按声明检查一次即可（声明级校验）。

- [ ] **Step 4: _check_schema_path 单段化**

`_check_schema_path`（expand.py 234-268）改为：仅 `len(segs) == 1` 合法（`this/<名>`）；2 段及以上一律 `scope.out_of_scope`（函数式传参后父块不再写/读直接子帧）。`_PLAIN_PATH` 正则（47 行）的 `_iter_schema_paths` 仍收集裸路径但都按单段校验。**注意**：此改动使旧的 `this/子块/变量` 写入在 Plan ② 起被拒——这是意图（跨帧寻址废除）。

- [ ] **Step 5: 运行确认通过**

Run: `conda run -n autobranch --no-capture-output python -m pytest tests/test_parser_expand.py tests/test_parser_checks.py tests/test_parser_vars.py -q`
Expected: PASS（旧测试若含跨帧 `this/子块/变量` 则需迁移为单段——见 Task 5）

- [ ] **Step 6: Commit**

```bash
git add autobranch/parser/expand.py autobranch/parser/models.py tests/test_parser_expand.py tests/test_parser_checks.py
git commit -m "feat(parser): function-call static validation (args/returns/output-set/single-segment)"
```

---

### Task 4: typed inputs 注入 schema_decl + 运行期类型感知

**Files:**
- Modify: `autobranch/orchestrator/context.py:66`（一行）
- Test: `tests/orchestrator/test_models.py:119`（若断言 `inputs == {}` 则迁移）

**Interfaces:**
- Consumes: Task 1 的 `BlockDecl.inputs: tuple[tuple[str,str],...]`
- Produces: `schema_decl` 返回的 `SchemaBlockDecl.inputs = {名: 类型}`（真实类型而非 `""`）

- [ ] **Step 1: 改 context.py**

`inputs={name: "" for name in decl.inputs}` → `inputs={name: typ for name, typ in decl.inputs}`。outputs 行不变（`{name: "" for name in decl.outputs}`）。

- [ ] **Step 2: 迁移受影响测试**

`tests/orchestrator/test_models.py:119`（断言 M3 decl `inputs == {}` 处）：若其构造的 ParserBlockDecl 现在带类型，断言改 `== {"username": "str"}` 之类。运行 `tests/orchestrator` 相关用例，修到绿。

Run: `conda run -n autobranch --no-capture-output python -m pytest tests/orchestrator/test_models.py tests/orchestrator/test_schema_frames.py -q`
Expected: PASS

> 说明：`_declared_type`（engine.py:498）因此从 `""` 变真实类型——运行期 extract 对声明类型输入的 coerce 开始生效（Plan ① 已接线）。这是期望行为；动态传参的运行时注入在 Plan ③。

- [ ] **Step 3: Commit**

```bash
git add autobranch/orchestrator/context.py tests/orchestrator/test_models.py
git commit -m "feat(orchestrator): inject typed block inputs into schema frames"
```

---

### Task 5: 全量测试/前端/E2E/文档迁移

**Files:**
- Modify: `tests/parser_fixtures.py`、`tests/test_parser_expand.py`、`tests/test_parser_checks.py`、`tests/test_parser_integration.py`、`tests/test_parser_vars.py`、`tests/server/conftest.py`、`tests/server/test_validation.py`、`tests/server/test_integration.py`、`tests/e2e/flows/订单审批.yaml`、`autobranch/frontend/src/features/tree-editor/model.ts:365-369`、`autobranch/frontend/src/features/tree-editor/yaml.test.ts:92-99`、`autobranch/frontend/e2e/workflow.spec.ts:20`
- Test: 全量

**Interfaces:**
- Consumes: 全部新语法（Task 1-3 产物）
- Produces: 全仓库 DSL 样例一致使用新语法；前端编辑器识别 `block ` 前缀

- [ ] **Step 1: 迁移剩余测试 fixture 与内联样例**

按 Task 1 Step 1 的映射迁移全部剩余文件（parser_fixtures.py 的 LOGIN/EXPORT/MAIN、test_parser_expand/checks/integration/vars 内联、server conftest/validation/integration、`订单审批.yaml`、e2e workflow.spec.ts）。`tests/test_parser_integration.py:73` 的 `LOGIN_YAML.replace("操作块 登录", ...)` 改为 replace `"block 登录"`。
`autobranch/frontend/src/features/tree-editor/model.ts:365-369`：`startsWith("操作块 ")` → `startsWith("block ")`；报错文案同步；yaml.test.ts 断言同步。

Run: `conda run -n autobranch --no-capture-output python -m pytest -q`
Expected: PASS（全量，原 772+ 附近）

- [ ] **Step 2: 前端回归**

Run（`autobranch/frontend`）: `npm.cmd test -- --run; npm.cmd run lint; npm.cmd run typecheck`
Expected: 全绿

- [ ] **Step 3: E2E 验证**

Run（`autobranch/frontend`）: `npm.cmd run test:e2e`
Expected: PASS（AGENTS 要求前端 E2E 必跑；workflow.spec.ts 已迁移新语法）

- [ ] **Step 4: 文档同步**

- `docs/contract.md`：§5.3.3 块接口（inputs dict 类型化）、§5.7.3 块引用（args/returns 替代写入）、§5.7.4 帧模型（函数式传参+单段作用域）、§5.3.2 作用域（单段）、变量语法 `[[ ]]` 替换 `{{ }}` 示例。
- `docs/specs/M2-behavior-tree-parser.md`：新语法 + 静态校验错误码。
- `docs/specs/M6-leaf-agent.md`：executor 正则同步说明（无需大改）。
- `docs/superpowers/specs/2026-09-08-block-function-call-design.md`：若实现与设计有偏差则微调（设计已是目标态）。
- `openspec/specs/behavior-tree-parser/spec.md`：块声明/ref 语法若被描述则同步新语法。

- [ ] **Step 5: lint + 全量回归**

Run: `conda run -n autobranch --no-capture-output python -m ruff check autobranch tests`
Run（`autobranch/frontend`）: `npm.cmd run lint`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "test+docs+frontend: migrate DSL samples to english function-call syntax"
```

---

## Self-Review 记录

> **执行策略（controller ruling，2026-09-09）：** 语法是全局键/前缀变更，按 Task 1-4 顺序会产生中间态"大部分 parser 测试红"，与 SDD 每任务全绿+commit 矛盾。**合并执行**：Task 1+2+Task5-Step1 合并为"语法+正则+全量 fixture 迁移"一个任务（结束时 parser/server 测试全绿）；Task 3（静态校验）、Task 4（typed inputs）各自独立；Task 5 剩余（前端/E2E/文档）收敛。每任务独立 commit + review。本 plan 其余内容不变。

**Spec 覆盖**：spec §1 语法（block/inputs dict/outputs/args/returns/废除写入、`[[ ]]`）→ Task 1/2；§4 两阶段校验（args⊆inputs/returns⊆outputs/inputs 全必填/output 全赋值/类型已注册/单段）→ Task 3；§5 作用域单段 → Task 3 Step 4；typed inputs → Task 4；测试/前端/E2E/文档 → Task 5。**未覆盖（明确 Plan ③）**：动态调用执行器、帧实例化、帧销毁、运行期 args 注入/returns 回收、`bindings`/`ParamBinding`/`FrameInfo` 移除。输出赋值点"存在即可、不分析分支路径"已实现于 Task 3 Step 3 注释。

**Placeholder 扫描**：无 TBD。Step 3 的 output 校验"语义决策"已写明（本块树内 set/returns，不深入 ref 子块，声明级）。

**类型一致性**：`BlockDecl.inputs` 在 document.py 构造（190/225/239）、expand.py 消费（537/549/551/567）、context.py（66）三处同步为新结构。IRNode.args/returns 在 document.py 构造、expand.py 消费（Task 3）。`TYPE_REGISTRY` 键全程引用。

**注意（执行者）**：
- Task 1 Step 4 保留 `bindings`/`ParamBinding` 但不再由 `写入` 填充——旧测试对 bindings 的断言（test_parser_refs.py:113/133/143）需在 Task 1 迁移时改为断言 args/returns。
- Task 3 Step 4 单段化会使所有旧的跨帧 `this/子块/变量` 测试失败——属意图，Task 5 迁移为单段语义（或删去不再合法的跨帧读写用例）。
- Task 3 output 校验对"ref 子块内部如何产出输出"不深入（该子块自校验）；若某测试构造了"块 B ref A 且 B 的 output 由 A 的 returns 供给"，赋值点 = B 的 returns 目标，应算已赋值。
- 全量回归在 Task 5 才跑；Task 1-4 之间仓库处于"语法迁移中"中间态（部分测试红），这是有意的顺序（每个 Task 内自洽、Task 5 收敛）。若环境要求每步全绿，请在 Task 1 一次性迁移 parser 全部 fixture 与测试（把 Task 5 Step 1 提前合并）。