# 参数语法重构实现计划（Param./NewParam. 统一读写记号）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将参数读写语法统一为 `Param.x`（读取）与 `NewParam.x[:type]`（新建），彻底废弃 `[[get:]]`/`[[set:]]`/`this/` 用户语法，并迁移存量树（中文变量名→语义英文名）。

**Architecture:** 后端解析器（`expand.py`）以新正则产出裸变量名与类型；执行器在叶子执行前确定性替换 `Param.x`；遍历器对 ref/FunctionCall 用 `Param.x` 解析实参、从 `NewParam.x` 键提取 returns 接收名；前端 validation 同步新语法并提供高亮输入框；迁移脚本按映射表改写 DB 存量树。

**Tech Stack:** Python 3.11（re 正则、sqlite3）、React 18 + TypeScript（前端高亮叠加层）。

**Spec:** `docs/superpowers/specs/2026-09-18-parameter-syntax-rework-design.md`

## Global Constraints

- 变量名 = ASCII 标识符 `[A-Za-z_][A-Za-z0-9_]*`（不得数字开头）。
- `Param.<name>` 边界 = 首个非 `[A-Za-z0-9_]` 字符（含中文即边界）。
- `NewParam.<name>[:<type>]`，type ∈ `{str,int,float,bool,page_ref,object}`，可省略。
- 反引号 `` ` `` 包裹的 `Param`/`NewParam` 为纯文本（不替换、去反引号）；未闭合反引号 → 校验错误。
- 旧语法 `[[get:...]]`、`[[set:...]]`、用户可见 `this/名` → 校验错误 `syntax.deprecated`，相关代码彻底清理。
- 引擎内部帧路径 `this/<名>` 保留为内部实现，用户侧一律裸名/`Param.`/`NewParam.`。
- ref/FunctionCall 的 **args** 只允许 `Param.x`（变量引用）或字面量，禁止 `NewParam`。
- **returns 接收名** = `NewParam.接收名`（键前缀），类型由 dict 值提供；内联 `:int` 兼容忽略。
- 全程中文注释/文档；conda 环境 `autobranch`；前端 workdir `autobranch/frontend`。
- 每次任务完成后运行相关测试；改动完成后即时 commit+push（AGENTS.md 第 6 条）。

---

### Task 1: 后端解析新语法（expand.py + models.py）

**Files:**
- Modify: `autobranch/parser/expand.py:38-111`（正则与迭代器）、`autobranch/parser/expand.py`（Action/Condition 展开处新增废弃/反引号校验）
- Test: `tests/test_parser_vars.py`（重写为新语法）

**Interfaces:**
- Consumes: 无（纯解析层）。
- Produces: `_iter_get_paths(text) -> list[str]`、`_iter_set_decls(text) -> list[tuple[str,str]]`、`_iter_schema_paths(text) -> list[str]`（全部返回**裸变量名**，行为与旧版一致，仅正则不同）；新校验函数 `_check_param_syntax(text) -> list[CheckIssue]`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_parser_vars.py` 新增/改写：

```python
def test_get_reference():
    from autobranch.parser.expand import _iter_get_paths
    assert _iter_get_paths("访问 Param.base_url 网站") == ["base_url"]

def test_get_boundary_at_chinese():
    assert _iter_get_paths("保存www.google.com参数到Param.base_url中") == ["base_url"]

def test_set_decl_with_type():
    from autobranch.parser.expand import _iter_set_decls
    assert _iter_set_decls("保存为 NewParam.appleAmount:int") == [("appleAmount", "int")]

def test_set_decl_no_type():
    assert _iter_set_decls("保存为 NewParam.base_url") == [("base_url", "")]

def test_backtick_escape_not_collected():
    assert _iter_get_paths("写 `Param` 这个词") == []
    assert _iter_set_decls("写 `NewParam` 这个词") == []
```

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n autobranch pytest tests/test_parser_vars.py -v`
Expected: FAIL（现有实现按 `[[get:...]]` 匹配，`Param.` 无匹配）。

- [ ] **Step 3: 实现新正则与迭代器**

在 `expand.py` 顶部替换：

```python
#: ``Param.<name>`` 读取引用（叶子执行前程序替换为真实值）；name 为 ASCII 标识符
_GET_TMPL = re.compile(r"Param\.([A-Za-z_][A-Za-z0-9_]*)")
#: ``NewParam.<name>[:type]`` 写入声明；type ∈ TYPE_REGISTRY token（可省略）
_SET_TMPL = re.compile(
    r"NewParam\.([A-Za-z_][A-Za-z0-9_]*)(?::(str|int|float|bool|page_ref|object))?"
)
#: 数字开头的非法变量名（Param.2x → 校验错误 syntax.invalid_name）
_INVALID_NAME_TMPL = re.compile(r"(?:Param|NewParam)\.(\d)")
#: 旧语法残留（[[get:/[[set:/用户可见 this/）→ 校验错误 syntax.deprecated
_DEPRECATED_TMPL = re.compile(r"\[\[\s*(?:get|set)\s*:|(?<![\w$])this/")
#: 反引号转义段（`` `Param` `` → 纯文本，不收集/不替换）
_BACKTICK = re.compile(r"`([^`]*)`")
```

`_iter_set_decls` / `_iter_get_paths` 改为对 `_BACKTICK.sub("", text)` 的结果做 finditer：

```python
def _iter_set_decls(text: str) -> list[tuple[str, str]]:
    decls: list[tuple[str, str]] = []
    for m in _SET_TMPL.finditer(_BACKTICK.sub("", text)):
        type_name = m.group(2) or ""
        path = m.group(1)
        if path:
            decls.append((path, type_name))
    return decls

def _iter_get_paths(text: str) -> list[str]:
    return [m.group(1) for m in _GET_TMPL.finditer(_BACKTICK.sub("", text)) if m.group(1)]
```

删除 `_PLAIN_PATH`；`_iter_schema_paths` 保留调用关系（get/set 已含全部），删除裸 this/ 分支：

```python
def _iter_schema_paths(text: str) -> list[str]:
    paths: list[str] = []
    paths.extend(_iter_get_paths(text))
    paths.extend(_iter_set_paths(text))
    return paths
```

新增校验函数（挂在 `expand_document` 主树展开前，对每个叶子 description 调用；`CheckIssue`/`make_issue`/`Loc` 沿用现有导入）：

```python
def _check_param_syntax(text: str, prefix: str, issues: list) -> None:
    if not isinstance(text, str) or not text:
        return
    if text.count("`") % 2 != 0:
        issues.append(make_issue(prefix, "syntax.unclosed_backtick", "反引号未闭合，`Param`/`NewParam` 需成对出现"))
    for m in _DEPRECATED_TMPL.finditer(text):
        issues.append(make_issue(prefix, "syntax.deprecated", "旧语法已废弃，请改用 Param.x / NewParam.x[:type]"))
    for m in _INVALID_NAME_TMPL.finditer(text):
        issues.append(make_issue(prefix, "syntax.invalid_name", "变量名不能以数字开头"))
```

在 `expand.py` 的 Action/Condition 展开分支（`_expand_ir`，约 L342-353 的 `ActionNode` 构造处）用 `_check_param_syntax(node.description, ...)` 收集问题（prefix 用现有节点 prefix 参数）。

`_bare_name`/`_schema_segments`/`_display_path` 保留（内部 `this/` 兼容仍可处理，但用户侧不再产出）。

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n autobranch pytest tests/test_parser_vars.py -v`
Expected: PASS。

- [ ] **Step 5: 补充废弃/反引号/非法名测试并跑通**

```python
def test_deprecated_get_rejected():
    from autobranch.parser.expand import _check_param_syntax
    issues = []
    _check_param_syntax("填 [[get:amount]]", "n1", issues)
    assert any(i.code == "syntax.deprecated" for i in issues)

def test_unclosed_backtick_rejected():
    issues = []
    _check_param_syntax("写 `Param", "n1", issues)
    assert any(i.code == "syntax.unclosed_backtick" for i in issues)

def test_invalid_name_rejected():
    issues = []
    _check_param_syntax("读 Param.2x", "n1", issues)
    assert any(i.code == "syntax.invalid_name" for i in issues)
```

Run: `conda run -n autobranch pytest tests/test_parser_vars.py -v`；Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add autobranch/parser/expand.py tests/test_parser_vars.py
git commit -m "feat(parser): 参数语法重构——Param./NewParam. 解析与旧语法/反引号/非法名校验"
```

---

### Task 2: 执行器与提示词改造（executor.py + prompts.py）

**Files:**
- Modify: `autobranch/leaf_agent/executor.py:75-117`（`_GET_TMPL`、`_resolve_get_refs`）、`autobranch/leaf_agent/prompts.py`（`PROMPT_VERSION` 与 `[[set]]` 文案）
- Test: `tests/leaf_agent/test_get_replace.py`（重写为新语法）

**Interfaces:**
- Consumes: Task 1 的 `_GET_TMPL` 语义（`Param.x` 裸名）。
- Produces: `_resolve_get_refs(description, ctx) -> tuple[str, str | None]`（签名不变，替换 `Param.x`；反引号内不替换、去反引号）。

- [ ] **Step 1: 写失败测试**

重写 `tests/leaf_agent/test_get_replace.py` 关键用例：

```python
def test_param_replaced():
    node = ActionNode(description="填金额 Param.amount")
    # space 预置 amount=100；断言替换后描述含 "100" 且无 "Param."
    ...

def test_param_backtick_not_replaced():
    # 描述 "写 `Param` 保留字，读 Param.amount" → 结果含 "写 Param 保留字" 且 amount 被替换
    ...

def test_param_undefined_failure():
    # "读 Param.未定义" → 返回 get_error，叶子 FAILURE
    ...
```

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n autobranch pytest tests/leaf_agent/test_get_replace.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现**

替换 `executor.py` 顶部：

```python
_GET_TMPL = re.compile(r"Param\.([A-Za-z_][A-Za-z0-9_]*)")
_BACKTICK = re.compile(r"`([^`]*)`")
```

重写 `_resolve_get_refs`（反引号段跳过替换；读失败返回错误）：

```python
def _resolve_get_refs(description: str, ctx: LeafContext) -> tuple[str, str | None]:
    if not _GET_TMPL.search(_BACKTICK.sub("", description)):
        return _BACKTICK.sub(r"\1", description), None
    if ctx.space is None:
        return description, "变量读取依赖 SchemaSpace（未注入 space）"
    frame = ctx.space._current
    parts = _BACKTICK.split(description)
    # 偶数下标为普通段（做替换），奇数下标为反引号转义段（原样保留）
    out: list[str] = []
    for idx, seg in enumerate(parts):
        if idx % 2 == 1:
            out.append(seg)
            continue
        replaced = seg
        for m in _GET_TMPL.finditer(seg):
            var = m.group(1)
            try:
                value = ctx.space.read(frame, var)
            except SchemaError as exc:
                return description, f"变量读取失败（{var}）: {exc}"
            if value is None:
                return description, f"变量未定义: {var}"
            replaced = replaced.replace(m.group(0), str(value))
        out.append(replaced)
    return "".join(out), None
```

`prompts.py`：`PROMPT_VERSION` 1.4 → 1.5；grep 该文件与 `tools.py` 中所有 `[[set`/`[[get` 文案，改为 `NewParam.x[:type]`/`Param.x` 教学（如产出型工具描述"目标须在 `NewParam.` 声明集内"）。`set_targets`/`set_decls` 已是裸名，无需改值。

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n autobranch pytest tests/leaf_agent/ -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add autobranch/leaf_agent/executor.py autobranch/leaf_agent/prompts.py tests/leaf_agent/test_get_replace.py
git commit -m "feat(leaf_agent): Param.x 确定性替换与反引号转义，提示词教学 NewParam."
```

---

### Task 3: 遍历器改造（traverser.py）

**Files:**
- Modify: `autobranch/orchestrator/traverser.py:471-486`（`_eval_arg`）、`_tick_ref`（约 L357-440 returns 回收）、`_tick_function_call`（约 L249-292 returns 回收）
- Test: `tests/orchestrator/test_ref_call.py`（重写为新语法）

**Interfaces:**
- Consumes: Task 1 语义（args 为 `Param.x` 或字面量；returns 键为 `NewParam.接收名`）。
- Produces: `_eval_arg(frame, expr)` 新语义；`_extract_return(name: str) -> tuple[str, str | None]`（剥离 `NewParam.` 前缀，`name:type` 拆类型）。

- [ ] **Step 1: 写失败测试**

在 `tests/orchestrator/test_ref_call.py` 改写传参/收返用例：

```python
def test_ref_arg_param_reference():
    # args: ["Param.username"] → 求值为父帧变量 username 的值
    ...

def test_ref_return_newparam_key():
    # returns: {"NewParam.result": "str"} → 回收后父帧新建变量 result
    ...
```

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n autobranch pytest tests/orchestrator/test_ref_call.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现**

`_eval_arg` 改为：

```python
_PARAM_REF = re.compile(r"Param\.([A-Za-z_][A-Za-z0-9_]*)")

def _eval_arg(self, frame, expr: str):
    m = _PARAM_REF.match(expr.strip())
    if m:
        var = m.group(1)
        if var not in frame.storage:
            return _MISSING
        return self.ctx.space.read(frame, var)
    return _parse_literal(expr)
```

新增模块级辅助：

```python
def _extract_return(name: str) -> tuple[str, str | None]:
    """returns 键 → (裸接收名, 内联类型或 None)。键形如 ``NewParam.名`` / ``NewParam.名:int``。"""
    n = name.strip()
    if n.startswith("NewParam."):
        n = n[len("NewParam."):]
    if ":" in n:
        n, inline = n.split(":", 1)
        return n.strip(), inline.strip() or None
    return n, None
```

在 `_tick_ref` / `_tick_function_call` 的 returns 回收处，用 `_extract_return(key)` 得到裸接收名（类型取 dict 值，若 dict 值为空则用内联类型），写入父帧变量名=裸接收名。args 求值已由 `_eval_arg` 覆盖。

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n autobranch pytest tests/orchestrator/ -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add autobranch/orchestrator/traverser.py tests/orchestrator/test_ref_call.py
git commit -m "feat(orchestrator): args 用 Param.x 解析、returns 用 NewParam. 键回收，消除裸名二义性"
```

---

### Task 4: 后端存量测试与全仓旧语法清理（后端部分）

**Files:**
- Modify: `tests/test_parser_onedoc_integration.py`、`tests/leaf_agent/test_get_replace.py`（其余）、`tests/test_parser_vars.py`（其余用例）、其它 `rg "\[\[(get|set):"` 命中的后端测试
- Test: 同上

**Interfaces:**
- Consumes: Task 1-3。

- [ ] **Step 1: 全仓定位旧语法**

Run:
```bash
conda run -n autobranch python -m pytest tests/ -q 2>&1 | tail -30
rg -l "\[\[(get|set):" autobranch tests -g "*.py"
```

- [ ] **Step 2: 逐一改写为等价新语法**

规则（保留语义/类型/数量）：
- `[[get:x]]` / `[[get:this/x]]` → `Param.x`
- `[[set:t:x]]` / `[[set:t:this/x]]` → `NewParam.x:t`
- `[[set:x]]`（无类型）→ `NewParam.x`
- 断言文本中的 `"[[get:"` 字样 → 对应新断言（如 `assert "[[get:" not in joined` → `assert "Param." not in joined`）
- ref/FunctionCall 的 args 裸变量名（命中声明变量）→ `Param.x`；returns 键裸名 → `NewParam.x`

- [ ] **Step 3: 全量后端测试**

Run: `conda run -n autobranch pytest tests/ -q`
Expected: PASS（无残留 `[[get:`/`[[set:`/`this/` 于测试描述）。

- [ ] **Step 4: ruff**

Run: `conda run -n autobranch ruff check autobranch tests scripts`
Expected: 无错误。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test: 后端测试全量迁移到 Param./NewParam. 新语法"
```

---

### Task 5: 前端 validation 与高亮组件

**Files:**
- Create: `autobranch/frontend/src/components/HighlightedField.tsx`
- Modify: `autobranch/frontend/src/features/tree-editor/validation.ts`（`SET_TMPL` L64 等）
- Test: `autobranch/frontend/src/components/HighlightedField.test.tsx`（新）、`autobranch/frontend/src/features/tree-editor/validation.test.ts`（若有则改）

**Interfaces:**
- Produces: `HighlightedField`（props 同 `TextField` + `multiline?: boolean`；渲染叠加层，`Param.x` 蓝色、`NewParam.x:int` 绿色，`data-testid` 透传）；validation 输出校验码新增 `syntax.unclosed_backtick`/`syntax.deprecated`/`syntax.invalid_name`。

- [ ] **Step 1: 写失败测试（HighlightedField）**

```tsx
it("高亮 Param 与 NewParam 记号", () => {
  render(<HighlightedField label="描述" value="访问 Param.base_url 并保存为 NewParam.网址:str" onChange={() => {}} />);
  expect(container.querySelectorAll(".hl-param")).toHaveLength(1);
  expect(container.querySelectorAll(".hl-newparam")).toHaveLength(1);
  expect(screen.getByTestId("hl-param-0")).toHaveTextContent("Param.base_url");
});

it("反引号转义不高亮", () => {
  render(<HighlightedField label="描述" value="写 `Param` 词" onChange={() => {}} />);
  expect(container.querySelectorAll(".hl-param")).toHaveLength(0);
});
```

- [ ] **Step 2: 运行确认失败**

Run: `npm.cmd test -- src/components/HighlightedField.test.tsx`
Expected: FAIL（组件不存在）。

- [ ] **Step 3: 实现 HighlightedField**

叠加层方案：外层 `position:relative` 容器；下层 `<div>` 渲染与 input 同字体/同 padding 的高亮文本（`Param.x`→`<span class="hl-param">`、`NewParam.x:int`→`<span class="hl-newparam">`，转义段原样）；上层原生 `<input>`/`<textarea>` 透明文字（`color: transparent`）+ `caret-color: initial`，同步滚动（textarea 用 `onScroll` 同步下层）。正则复用 `(?:Param|NewParam)\.([A-Za-z_][A-Za-z0-9_]*)(?::(str|int|float|bool|page_ref|object))?`，反引号段跳过。保留 `label`、`disabled`、`placeholder`、`data-testid`、`value`、`onChange` 语义（其余 props 透传）。

- [ ] **Step 4: validation.ts 改造**

`SET_TMPL` → `NewParam` 正则；新增 get 正则（`Param.`）、非法名/反引号/旧语法检测；`collectDeclaredVars` 的 set 目标与 returns 键处理：returns 键剥 `NewParam.` 前缀后计入声明变量；args 变量识别（`exprIsVariable`）改 `Param.` 前缀命中；`type_mismatch` 字面量校验逻辑保留。同步修改 validation 相关测试。

- [ ] **Step 5: 运行前端检查**

Run: `npm.cmd run typecheck && npm.cmd run lint && npm.cmd test`
Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add autobranch/frontend/src/components/HighlightedField.tsx autobranch/frontend/src/features/tree-editor/validation.ts
git commit -m "feat(frontend): 新增 Param/NewParam 高亮输入框与 validation 新语法"
```

---

### Task 6: 前端字段接入高亮与 returns/args 语法

**Files:**
- Modify: `autobranch/frontend/src/features/tree-editor/PropertyPanel.tsx`（描述字段、ref/FunctionCall 的 args/returns 接收名输入框换 `HighlightedField`）
- Test: `autobranch/frontend/src/features/tree-editor/PropertyPanel.test.tsx`

**Interfaces:**
- Consumes: Task 5 的 `HighlightedField` 与 validation 新语义。
- Produces: 属性面板各字段使用 `HighlightedField`；returns 接收名输入框语义 = `NewParam.接收名`。

- [ ] **Step 1: 替换字段**

Action 描述、Step expect、IfThenElse if、LoopUntil until、Branch when 用 `HighlightedField`；ref/FunctionCall 的 args 输入框与 returns「接收参数名」输入框换 `HighlightedField`（保留原有 `data-testid`）。

- [ ] **Step 2: 更新 PropertyPanel 测试**

改 returns 用例：接收名断言含 `NewParam.`（如 `ref-return-name-r2-0` 值为 `NewParam.结果`）；args 用例可含 `Param.`。新增一条：描述含 `Param.x` 时高亮渲染。

- [ ] **Step 3: 前端检查**

Run: `npm.cmd run typecheck && npm.cmd run lint && npm.cmd test`
Expected: 全绿。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(frontend): 属性面板字段接入 Param/NewParam 高亮，returns 接收名统一 NewParam."
```

---

### Task 7: DB 存量树迁移

**Files:**
- Create: `scripts/migrate_param_syntax.py`
- Data: `data/autobranch.db`

**Interfaces:**
- Consumes: 映射表（见下）、Task 1 的解析函数（可选复用）。
- Produces: 迁移后的 DB 树内容（`Param.x`/`NewParam.x:t`，变量名 ASCII）。

- [ ] **Step 1: 写迁移脚本**

`scripts/migrate_param_syntax.py`：
- `MAPPING = {"苹果金额": "appleAmount", "香蕉金额": "bananaAmount", "水果合计": "fruitTotal", "结果": "result", "入参1": "input1"}`。
- `migrate_content(content) -> str`：按行处理 YAML：
  - 文本替换（先长后短，避免部分覆盖）：`苹果金额`→`appleAmount` 等（作用于描述文本、args、returns 键）。
  - 旧语法重写：`[[get:X]]`/`[[get:this/X]]` → `Param.<新名>`；`[[set:t:X]]`/`[[set:t:this/X]]` → `NewParam.<新名>:t`；`[[set:X]]` → `NewParam.<新名>`。
  - returns 键（`<旧名>: <type>` 行，键含中文或裸名）→ `NewParam.<新名>: <type>`；args 列表项（裸名命中声明变量）→ `Param.<新名>`（字面量如 `"2"`、`"3"` 不变）。
  - 文档 inputs 键 / outputs 列表项：裸名替换为映射名。
- `dry_run = "--apply" not in sys.argv`：dry-run 打印每树 diff（`difflib`）不写库；`--apply` 写回 `trees.content`（按 id UPDATE）。
- 幂等：对已迁移内容再次运行无变化（替换已在映射外的残留）。

- [ ] **Step 2: dry-run 审查**

Run: `conda run -n autobranch python scripts/migrate_param_syntax.py`
Expected: 输出 8 棵树的逐行 diff；人工确认映射与语法重写正确（重点：表格求和演示、test333）。

- [ ] **Step 3: apply**

Run: `conda run -n autobranch python scripts/migrate_param_syntax.py --apply`
Expected: 写回成功；重跑 dry-run 显示无 diff（幂等）。

- [ ] **Step 4: 校验迁移后树可解析**

Run: `conda run -n autobranch python -c "from autobranch.parser.onedoc import parse; from autobranch.server.db import session; [print(t.name, len(parse(t.content).issues or [])) for t in session.query(...)]"`（或直接跑 `pytest` 集成/后端 `check` API）。确认无 `syntax.deprecated` 问题。

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_param_syntax.py
git commit -m "feat(scripts): 参数语法迁移脚本（中文变量名→语义英文 + 旧语法→Param./NewParam.）"
```

---

### Task 8: E2E 与文档示例重写

**Files:**
- Modify: `autobranch/frontend/e2e/function-call.spec.ts`、`workflow.spec.ts`、`ref-call.spec.ts`；`README.md`；`docs/contract.md`（§5.3/§5.7.3/§5.10/§13）；`docs/specs/M1/M2/M4/M5/M9-frontend-ui.md`；`openspec/specs/*`（schema-namespace、leaf-agent、behavior-tree-parser、tree-editor）
- Test: 上述 E2E

**Interfaces:**
- Consumes: 映射表（Task 7）。

- [ ] **Step 1: E2E 改写**

`function-call.spec.ts`：`苹果金额`→`appleAmount`、`香蕉金额`→`bananaAmount`、`水果合计`→`fruitTotal`、`结果`→`result`；`returns:` 键 → `NewParam.<名>`；描述内 `[[set:int:苹果金额]]` → `NewParam.appleAmount:int`；断言黑板变量名同步（如 `blackboard.locator("tr", { hasText: "appleAmount" })` 与 `155`）。
`workflow.spec.ts` / `ref-call.spec.ts`：同样规则（ref 的 args 用 `Param.x`、returns 键 `NewParam.x`）。

- [ ] **Step 2: 文档改写**

grep `rg -n "\[\[(get|set):|this/" docs README.md openspec` 逐处改写为新语法与映射名；`docs/specs/M4-leaf-agent.md` 的 `PROMPT_VERSION` 说明同步 1.5；`M1`/`M2`/`contract.md` 的变量读写语法段落改写。

- [ ] **Step 3: 前端/后端全量检查**

Run: `conda run -n autobranch pytest tests/ -q`；`conda run -n autobranch ruff check autobranch tests scripts`
Run: `npm.cmd run typecheck && npm.cmd run lint && npm.cmd test`
Expected: 全绿。

- [ ] **Step 4: E2E（后端 8001 + 前端 5174 运行中）**

Run: `npx.cmd playwright test e2e/function-call.spec.ts -g F1`（渲染）；F2/C1/F5 执行用例依赖 LLM 环境，尽力运行。
Expected: F1 通过；执行用例视环境而定。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs+e2e: 参数语法重构——E2E 与文档示例迁移到 Param./NewParam."
```

---

### Task 9: 全量验收

**Files:**
- 无新增

**Interfaces:**
- Consumes: 全部任务。

- [ ] **Step 1: 后端全量**

Run: `conda run -n autobranch pytest tests/ -q`
Run: `conda run -n autobranch ruff check autobranch tests scripts`
Expected: 全绿。

- [ ] **Step 2: 前端全量 + 构建**

Run: `npm.cmd run typecheck && npm.cmd run lint && npm.cmd test && npm.cmd run build`
Expected: 全绿。

- [ ] **Step 3: 真实树运行验收（用户验证目标）**

后端 8001 + 前端 5174 运行中，真实浏览器打开迁移后的「表格求和演示」与「test333」：确认编辑器高亮、ref/FunctionCall 参数面板正常、`/api/functions` 列表正常；触发执行并查看报告（LLM 环境允许时），变量名显示为 `appleAmount`/`fruitTotal` 等。

- [ ] **Step 4: 最终提交推送**

```bash
git add -A
git commit -m "chore: 参数语法重构全量验收通过"
git push
```

## Self-Review

- **Spec 覆盖**：A（语法）→ Task1/2/3/5；B（引擎）→ Task1/2/3；C（前端）→ Task5/6；D（迁移）→ Task7/8；E（测试）→ 各 Task + Task9。设计文档 §2.4「内部 this/ 保留」→ Task1 保留 `_bare_name`、Task3 不碰内部路径。
- **占位符扫描**：各 Task 含具体代码/命令/预期，无 TBD。
- **类型一致**：`_iter_get_paths`/`_iter_set_decls`/`_iter_schema_paths` 签名在各 Task 一致；`_resolve_get_refs` 签名不变；`_extract_return` 在 Task3 定义并被其自身使用；`HighlightedField` props 语义同 TextField。