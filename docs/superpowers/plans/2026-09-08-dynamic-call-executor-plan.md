# Plan ③：动态调用执行器（ref 运行时函数调用 + 帧实例化）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 ref 从"静态内联展开"改为"运行时动态调用"：ref 保留为调用节点（RefNode），运行期遇 ref 时动态建子帧、按 args 注入实参（coerce 到输入类型）、递归执行被引用块的可执行树、按 returns 回收输出到父帧局部变量、退出。帧对象保留到整个行为树执行结束才释放；运行期通过激活帧控制访问（`resolve_target` 单段化）。

**Architecture:** 解析层：每块独立预展开为基础树（ref 处生成 `RefNode` 不再内联），`ParseResult` 新增 `blocks_tree: dict[str, Node]`（块名→可执行基础树）。运行层：`Traverser` 遇 `RefNode` 走 `_tick_ref`：求值 args（父帧 `this/x` 或字面量）→ coerce 到输入类型 → `enter_block`（注入 inputs/decl）→ 递归 tick 子块树 → SUCCESS 按 returns 写父帧 → `exit_block`。移除 `node.frame` 字符串驱动（`_sync_frame` 退役）；`resolve_target` 收紧单段 `this/<名>`（M3 与 parser 一致）。移除 ParamBinding/bindings/FrameInfo 遗留。

**Tech Stack:** Python 3.11, dataclass, pytest。

**Spec:** `docs/superpowers/specs/2026-09-08-block-function-call-design.md`（§3 执行模型、§4 两阶段校验、§5 作用域、§6 模块影响）

## Global Constraints

- 全程中文对话与文档；代码标识符英文。
- conda 环境 `autobranch`：`conda run -n autobranch --no-capture-output python -m pytest ...`。前端命令在 `autobranch/frontend` 用 `npm.cmd`。
- 已定关键决策（controller rulings，勿改）：
  - **blocks_tree**：`ParseResult.blocks_tree: dict[str, Node]`（每块预展开基础树）；`Engine.run(tree, blocks, config)` 签名**不变**，`RunContext` 新增 `blocks_tree` 字段；server 调用面不变（从 `result` 多取一个字段传入 Engine 或 RunContext）。
  - **帧生命周期**：帧对象保留到**整个行为树执行结束**才释放（每次 run 新建 SchemaSpace 已实现释放）；执行期间激活帧控制访问权限。
  - **resolve_target 单段化**：M3 `resolve_target` 收紧为仅 `this/<名>` 单段（自身帧）；不再支持 `this/子块/变量`。
  - **RefNode**：models.py 新增 `RefNode(Node)`（`ref_target`/`args`/`returns`）。
  - **node.frame 退役**：Node.frame 字段移除；expand 不再写 frame 字符串；traverser `_sync_frame` 退役。
  - **遗留移除**：`ParamBinding`、`ParseResult.bindings`、`FrameInfo`、`ParseResult.frames` 移除。
  - 静态校验（Plan ②）保留：args⊆inputs、returns⊆outputs、inputs 全必填、output 全赋值、环/深度检测。
  - `snapshot_variables` 递归子帧展示不变（黑板全链）。

---

### Task 1: parser 改造——RefNode + blocks_tree + 每块独立预展开

**Files:**
- Modify: `autobranch/parser/models.py`（Node 去 frame、新增 RefNode、ParseResult 结构）
- Modify: `autobranch/parser/expand.py`（_expand_ref 生成 RefNode；每块独立预展开；移除 FrameInfo/ParamBinding）
- Modify: `autobranch/parser/parser.py`（ParseResult 构造）
- Modify: `autobranch/parser/document.py`（若引用 frame 相关）
- Test: `tests/test_parser_models.py`、`tests/test_parser_refs.py`、`tests/test_parser_integration.py`

**Interfaces:**
- Consumes: Plan ② 的 `BlockDecl.inputs: tuple[tuple[str,str],...]`、IRNode.args/returns
- Produces:
  - `RefNode(Node)`: `ref_target: str`, `args: tuple[tuple[str,str],...]`, `returns: tuple[tuple[str,str],...]`
  - `ParseResult`: `tree: BehaviorTree`（根块基础树，ref 保留 RefNode）, `blocks: dict[str, BlockDecl]`, `blocks_tree: dict[str, Node]`（**新增**，含根块与全部命名块预展开树）, `checks: CheckReport`；**移除** `bindings`/`frames`
  - `BehaviorTree.name` 仍 = 根块名；`tree.root` 为根块基础树（=`blocks_tree[根块名]`）

- [ ] **Step 1: 写失败测试（tests/test_parser_refs.py 改造）**

```python
def test_ref_becomes_refnode_not_inlined():
    doc = {"block 主": {"Sequence": [{"ref": "this/登录", "args": {"u": "this/a"}, "returns": {"r": "this/b"}}]},
           "block 登录": {"inputs": {"u": "str"}, "outputs": "r", "Sequence": [{"Step": {"action": "x"}}]}}
    result = parse_doc(doc)   # 现有 helper
    ref_node = result.tree.root.children[0]
    assert isinstance(ref_node, RefNode)
    assert ref_node.ref_target == "this/登录"
    assert ref_node.args == (("u", "this/a"),)
    assert ref_node.returns == (("r", "this/b"),)

def test_blocks_tree_contains_each_block():
    doc = {"block 主": {"Sequence": [{"ref": "this/登录"}]},
           "block 登录": {"Sequence": [{"Step": {"action": "x"}}]}}
    result = parse_doc(doc)
    assert set(result.blocks_tree) == {"主", "登录"}
    assert result.blocks_tree["主"] is result.tree.root   # 根块树与 tree.root 同一
```

Run: `conda run -n autobranch --no-capture-output python -m pytest tests/test_parser_refs.py -q`
Expected: FAIL（RefNode/blocks_tree 不存在）

- [ ] **Step 2: models.py——Node 去 frame、新增 RefNode、ParseResult 重构**

`autobranch/parser/models.py`：
```python
@dataclass(frozen=True)
class Node:
    loc: Loc | None = None          # frame 字段移除

@dataclass(frozen=True)
class RefNode(Node):
    """块引用调用节点：运行期动态调用被引用块。

    :param ref_target: 如 ``this/登录`` / ``文档名/登录``。
    :param args: ``(形参名, 实参表达式)``；实参 = 父帧裸路径 ``this/<名>`` 或字面量。
    :param returns: ``(输出名, 父帧目标变量)``；子块 SUCCESS 后回收写入父帧。
    """
    ref_target: str = ""
    args: tuple[tuple[str, str], ...] = ()
    returns: tuple[tuple[str, str], ...] = ()
```
- 删除 `ParamBinding` 类（models.py:197-215）、`FrameInfo` 类（218-231）、`ParseResult.bindings`/`frames` 字段；`ParseResult` 新增 `blocks_tree: dict[str, Node] = field(default_factory=dict)`（frozen dataclass 的 dict 默认值需 `field(default_factory=dict)`）。
- `BehaviorTree` 不变（name/root）。

- [ ] **Step 3: expand.py——每块独立预展开 + _expand_ref 生成 RefNode**

- 新增 `_expand_block_ir(ir, block_name, ctx) -> Node`：对单块 IR 展开为基础树（不含 ref 内联；遇 ref 生成 RefNode）。复用现有 `_expand_ir` 但遇 `kind == "ref"` 走新分支。
- `_expand_ref`（552-652）改：**不再内联**（删除 `_expand_ir(t_node, ...)` 递归与 `child_frame`/`FrameInfo`/`ctx.stack.push`）；保留静态校验（target 存在/环/深度/args⊆inputs/returns⊆outputs/inputs 全必填/实参作用域单段）；返回 `RefNode(ref_target=target, args=node.args, returns=node.returns, loc=loc)`。环/深度检测保留（静态，RefNode 运行时也会受同样限制）。
- `expand_document`（214-234）：改为对**每块**调用 `_expand_block_ir`，根块树 = `tree`，全部块树存入 `blocks_tree`；移除 `ctx.frames.append(FrameInfo...)` 与 `ExpansionResult.frames/bindings`（bindings 恒空）。`_check_all_block_outputs` 保留（块树现为独立基础树，仍可走查）。
- `ExpansionResult`（180-187）改字段：`tree`/`blocks_tree`/`issues`。
- 删除 `FrameInfo` 构造、`ctx.bindings`/`ParamBinding` 收集。
- `Node` 构造不再传 `frame=`（expand.py 全部 `frame=frame` 处删除该参数）。

- [ ] **Step 4: parser.py——ParseResult 构造**

`BehaviorTreeParser.parse`（39-68）：`ParseResult(tree=BehaviorTree(name=root, root=expansion.tree), blocks=..., blocks_tree=expansion.blocks_tree, checks=...)`。

- [ ] **Step 5: 迁移受影响测试断言**

- `tests/test_parser_models.py:90-105`：`frames`/`bindings` 断言移除；改 `blocks_tree` 断言。
- `tests/test_parser_refs.py:112-129`：`frames` 映射断言改 `blocks_tree`；`test_bindings_always_empty_in_result`（145-149）删除。
- `tests/test_parser_integration.py:52-54/90`：`bindings`/`frames` 断言移除。
- `tests/test_parser_expand.py`：若断言 frame 字符串则移除（多数不涉及）。

Run: `conda run -n autobranch --no-capture-output python -m pytest tests/test_parser_refs.py tests/test_parser_models.py tests/test_parser_integration.py tests/test_parser_expand.py tests/test_parser_document.py -q`
Expected: PASS

- [ ] **Step 6: ruff + Commit**

```bash
conda run -n autobranch --no-capture-output python -m ruff check autobranch/parser tests/test_parser_refs.py tests/test_parser_models.py tests/test_parser_integration.py
git add autobranch/parser/ tests/
git commit -m "feat(parser): RefNode + blocks_tree, remove static frame/bindings/frames"
```

---

### Task 2: schema 层单段化 + 帧语义

**Files:**
- Modify: `autobranch/schema/path.py`（resolve_target 单段）、`autobranch/schema/space.py`（exit_block docstring、snapshot 不变）
- Test: `tests/test_schema_scope.py`、`tests/test_schema_blackboard.py`、`tests/test_schema_integration.py`

**Interfaces:**
- Consumes: 无新依赖
- Produces: `resolve_target(frame, "this/x") -> (frame, "x")`；多段路径一律 `SchemaScopeError`

- [ ] **Step 1: 写失败测试**

`tests/test_schema_scope.py` 新增：
```python
def test_multisegment_rejected():
    space = SchemaSpace()
    t = space.enter_block("T")
    with pytest.raises(SchemaScopeError):
        space.write(t, "$this/子块/x", 1, "int")   # 子帧多段不再合法
```
> 现有 `test_schema_scope.py` 中含"直接子块写/读合法"的用例需迁移为拒绝。

Run: `conda run -n autobranch --no-capture-output python -m pytest tests/test_schema_scope.py -q`
Expected: FAIL

- [ ] **Step 2: path.py 单段化**

`resolve_target`（path.py:36-64）改为：仅 `_is_self(first) or first == frame.block_name` → `rest = segments[1:]`；`len(rest) != 1` → 越权；删除 `first in frame.children` 分支与孙级检查。`THIS_TOKEN`/`_SELF_TOKENS` 保留（兼容 `$this`）。
`split_segments` 不变。

- [ ] **Step 3: space.py 帧语义注释**

`exit_block`（84-92）docstring 更新：帧数据保留至行为树执行结束（供黑板上报）；「释放」= 退出激活栈。`snapshot_variables`（193-220）不变（递归子帧展示全链）。

- [ ] **Step 4: 迁移受影响测试**

`tests/test_schema_scope.py` 中"父写/读直接子块"合法用例 → 改拒绝断言；`tests/test_schema_blackboard.py`（若含 `this/子块/` 路径快照）→ 若展示用则保留（snapshot 是递归展示，非寻址）；`tests/test_schema_integration.py` 若含多段写 → 迁移。

Run: `conda run -n autobranch --no-capture-output python -m pytest tests/test_schema_scope.py tests/test_schema_blackboard.py tests/test_schema_integration.py tests/test_schema_config.py tests/test_schema_page.py -q`
Expected: PASS

- [ ] **Step 5: ruff + Commit**

```bash
git add autobranch/schema/ tests/test_schema_scope.py tests/test_schema_blackboard.py tests/test_schema_integration.py
git commit -m "feat(schema): single-segment resolve_target, frames live until run end"
```

---

### Task 3: Traverser 动态调用执行器

**Files:**
- Modify: `autobranch/orchestrator/traverser.py`（tick/_dispatch/_tick_ref；移除 _sync_frame/node.frame）
- Modify: `autobranch/orchestrator/context.py`（RunContext 加 blocks_tree）
- Modify: `autobranch/orchestrator/engine.py`（Engine.run 传 blocks_tree；get_exec_state 不变）
- Modify: `autobranch/server/services/engine.py`（run 传 blocks_tree）
- Test: `tests/orchestrator/`（helpers + 新 RefNode 用例）

**Interfaces:**
- Consumes: Task 1 的 `ParseResult.blocks_tree`、Task 2 的单段 resolve_target；`RefNode`；Plan ② 的 typed `BlockDecl.inputs`
- Produces:
  - `RunContext.blocks_tree: dict[str, Node]`
  - `Traverser._tick_ref(node: RefNode) -> NodeStatus`：动态调用
  - `Traverser` 不再依赖 node.frame；`_sync_frame` 删除

- [ ] **Step 1: 写失败测试（新增 tests/orchestrator/test_ref_call.py）**

```python
def test_ref_injects_args_and_receives_returns():
    # 构造：主块 ref 登录（args username→子帧；returns result→this/结果）
    # StubLeaf 在登录块内读 this/username（由注入的 args 写入）
    # 断言：子帧 inputs.username == 注入值；执行后父帧 this/结果 == 登录输出
```

具体构造（参照 make_run_context + StubLeaf 模式，但用 blocks_tree + RefNode）：
```python
login_tree = seq(
    action("填 [[get:this/username]]"),          # 读注入的形参
    action("输出 [[set:str:this/result]]"),
)
main_tree = seq(
    RefNode(ref_target="this/登录",
            args=(("username", "this/账号"),),
            returns=(("result", "this/结果"),)),
)
blocks_tree = {"主": main_tree, "登录": login_tree}
# make_run_context(...blocks=..., blocks_tree=blocks_tree)
# root = BehaviorTree("主", main_tree)
# 先在主帧 set this/账号 = "admin"
# tick → 断言 space 中 登录 帧 inputs["username"]=="admin"；主帧 this/结果 == "成功输出"
```
> 用测试 helper：`make_run_context` 需支持 `blocks_tree` 参数；StubLeaf 对 `[[get:this/username]]` 的替换走真实 executor（用 `make_default_leaf_executor(config, space)` 或简化：在测试里手工 `space.read` 断言）。

Run: `conda run -n autobranch --no-capture-output python -m pytest tests/orchestrator/test_ref_call.py -q`
Expected: FAIL

- [ ] **Step 2: context.py 加 blocks_tree**

`RunContext`（context.py:29-48）加字段 `blocks_tree: dict[str, Node] = field(default_factory=dict)`。`schema_decl` 不变（blocks 仍为声明表）。

- [ ] **Step 3: engine.py 传 blocks_tree**

`Engine.run`（65-70）签名不变；从哪拿 blocks_tree？——`Engine.run` 当前只收 `(tree, blocks, config)`。**方案**：`Engine.run` 增加可选参数 `blocks_tree: dict[str, Node] | None = None`（默认空 dict → 无 ref 的场景仍可用）；`RunContext.blocks_tree = blocks_tree or {}`。server 调用 `engine.run(result.tree, result.blocks, config, result.blocks_tree)`。

- [ ] **Step 4: traverser.py 动态调用**

- `tick`（98-122）：删除 `_sync_frame(node.frame)` 与 `_sync_frame(prev)`（帧由 `_tick_ref` 管理）。
- `_dispatch`（126-139）加分支：`if isinstance(node, RefNode): return self._tick_ref(node)`。
- 新增 `_tick_ref`：
```python
def _tick_ref(self, node: RefNode) -> NodeStatus:
    target = (node.ref_target or "").strip()
    parts = [p for p in target.split("/") if p]
    if len(parts) != 2:
        return self._note_failure(node, f"ref 目标非法: {target!r}") or FAILURE
    block_name = parts[1]
    child_tree = self.ctx.blocks_tree.get(block_name)
    if child_tree is None:
        return self._note_failure(node, f"引用块未在 blocks_tree 中: {block_name!r}") or FAILURE
    decl = self.ctx.schema_decl(block_name)
    space = self.ctx.space
    parent = self.ctx.current_frame
    # 1) 求值 args：裸路径 this/<名> → 父帧读；字面量原样
    args_values = {}
    for arg_name, expr in node.args:
        val = self._eval_arg(parent, expr)
        if val is _MISSING:
            return self._note_failure(node, f"实参 '{arg_name}' 求值失败: {expr!r}") or FAILURE
        args_values[arg_name] = val
    # 2) coerce 到输入类型
    typed = {}
    input_types = {n: t for n, t in (decl.inputs.items() if decl else {}).items()}
    for name, val in args_values.items():
        t = input_types.get(name, "")
        typed[name] = coerce(t, val) if t else val
    # 3) 建子帧（注入 inputs/config）
    frame = space.enter_block(block_name, decl)
    for name, val in typed.items():
        space.write(frame, f"this/{name}", val, input_types.get(name, "") or infer_type(val))
    try:
        # 4) 递归执行子块树（不额外管理帧——子块内部 ref 由各自的 _tick_ref 管理）
        status = self.tick(child_tree)
        # 5) SUCCESS → returns 回收写父帧
        if status == SUCCESS:
            for out_name, target_var in node.returns:
                rel = _single_segment(target_var)   # 取 this/<名> 的 <名>
                if rel is None:
                    continue
                value = space.read(frame, f"this/{out_name}")   # 子帧读输出
                if value is not None:
                    space.write(parent, f"this/{rel}", value, infer_type(value))
    finally:
        # 6) 退出子帧（数据保留至 run 结束）
        space.exit_block()
    return status
```
辅助：`_eval_arg(frame, expr)`：`expr` 为 `this/<名>` 裸路径 → `space.read`；否则视为字面量（str/int/float/bool）。`_single_segment(path)`：`this/x` → `"x"`，其余 None。`_MISSING` 哨兵。
- `_note_failure`（299-306）`loc` 兜底改 `node.loc.path` 或空串（不再用 node.frame）。
- `count_nodes`（64-79）与 `node_type_name`（40-54）加 RefNode 分支（RefNode 计 1，不计子块——子块树独立计数由 tick 递归）。
- 删除 `_sync_frame`（258-280）。

> 注意：根帧由 `Engine.run` 建（`space.enter_block(tree.name, ...)`）；`_tick_ref` 建子帧基于当前激活帧。`space.exit_block()` 不传参（退当前）。

- [ ] **Step 5: 迁移 helpers 与现有测试**

- `tests/orchestrator_helpers.py`：6 个工厂删除 `frame=` 参数（Node 无 frame）；`make_run_context` 加 `blocks_tree` 参数。
- `tests/orchestrator/test_engine_integration.py`：删除 frame 字符串参数；`test_success_path_aggregation` 改无 frame。
- `tests/orchestrator/test_schema_frames.py`：帧序列断言改为"用 RefNode 驱动的 `_tick_ref` 建帧/退帧"或用 `blocks_tree` + 手工 tick 断言 `space._current` 序列。`test_same_name_variables_isolated` 保留（隔离语义不变）。配置继承用例改用 blocks_tree 块声明。
- `tests/leaf_agent`、`tests/engine`：确认不受影响（它们直接构造帧/space，不依赖 node.frame）。

Run: `conda run -n autobranch --no-capture-output python -m pytest tests/orchestrator tests/leaf_agent tests/engine tests/server -q`
Expected: PASS

- [ ] **Step 6: 全量回归 + 前端**

Run: `conda run -n autobranch --no-capture-output python -m pytest -q`
Run（`autobranch/frontend`）: `npm.cmd test -- --run; npm.cmd run lint; npm.cmd run typecheck; npm.cmd run test:e2e`
Expected: 全绿

- [ ] **Step 7: ruff + Commit**

```bash
conda run -n autobranch --no-capture-output python -m ruff check autobranch tests
git add autobranch/orchestrator/ autobranch/server/services/engine.py tests/
git commit -m "feat(engine): dynamic ref call (RefNode → frame inject/returns/exit)"
```

---

### Task 4: 文档同步 + 收尾

**Files:**
- Modify: `docs/contract.md`、`docs/specs/M7-orchestrator.md`、`docs/specs/M3-schema-namespace.md`、`openspec/specs/orchestrator/spec.md`（若有）、`openspec/specs/schema-namespace/spec.md`（帧语义）
- Test: 无（文档）

**Interfaces:**
- Consumes: 全部新语义

- [ ] **Step 1: contract.md**

- §5.7.4 帧模型：更新为"运行期动态调用帧；帧保留至行为树结束；激活帧控制访问；单段寻址"。
- §5.7.3：ref 运行期为动态调用（补运行时注入/回收语义）。
- 移除/更新 `node.frame` 相关措辞（若有）。

- [ ] **Step 2: M7 spec**

`docs/specs/M7-orchestrator.md`：Traverser 更新为 RefNode 动态调用、blocks_tree、移除 _sync_frame 描述。

- [ ] **Step 3: M3 spec + openspec**

`docs/specs/M3-schema-namespace.md`：resolve_target 单段化说明。`openspec/specs/schema-namespace/spec.md`：帧生命周期（保留至 run 结束 + 激活帧控制）。`openspec/specs/orchestrator/spec.md`（若存在）同步。

- [ ] **Step 4: 全量验证 + Commit**

Run: `conda run -n autobranch --no-capture-output python -m pytest -q; conda run -n autobranch --no-capture-output python -m ruff check autobranch tests`
Run（`autobranch/frontend`）: `npm.cmd test -- --run; npm.cmd run typecheck`
```bash
git add docs/ openspec/
git commit -m "docs: sync dynamic ref-call executor and frame lifecycle (Plan ③)"
```

---

## Self-Review 记录

**Spec 覆盖**：spec §3（动态调用/帧实例化/args 注入/returns 回收/帧即调用栈）→ Task 3；§4 阶段一静态校验保留（Task 1）、阶段二运行期求值+coerce（Task 3 `_tick_ref`）；§5 单段作用域（Task 2 resolve_target 单段 + parser 已单段）；§6 模块影响（Task 1-4）。**已定决策**：blocks_tree 载体（ParseResult 字段 + Engine.run 可选参）、帧保留至 run 结束（用户确认）、resolve_target 单段化（用户确认）。

**Placeholder 扫描**：无 TBD。`_tick_ref` 给出完整代码。辅助函数（`_eval_arg`/`_single_segment`）签名明确。

**类型一致性**：`RefNode` 在 models.py 定义、expand.py 生成、traverser `_dispatch`/`_tick_ref` 消费、`count_nodes`/`node_type_name` 处理。`blocks_tree` 在 ParseResult 定义、parser.py 填充、Engine.run 可选参、RunContext 字段、traverser 消费。`coerce`/`infer_type` 来自 Plan ①。

**注意（执行者）**：
- Task 3 的 `_tick_ref` 中 `space.write(parent, f"this/{rel}", ...)` 写父帧——`parent` 是进入子帧前的激活帧（`self.ctx.current_frame` 在 enter_block 前取）。写父帧用 `this/x`（单段）合法。
- 跨文档 ref：`blocks_tree` 需含跨文档块（`load_block` 的 doc_cache 中所有块）。expand 的 `blocks_tree` 应收集根文档 + 所有被 ref 引用的跨文档块。若跨文档块未预展开，`_tick_ref` 找不到 → 运行时报错。**Task 1 的 `_expand_block_ir` 需遍历所有加载的文档块**（`ctx.doc_cache` + 根文档）。
- `snapshot_variables` 递归子帧展示全链保留（黑板需求，用户确认）。
- `get_exec_state`（engine.py:128-142）用 `snapshot_variables(current_frame)`——因帧保留，展示激活帧起全链；若需展示根起全链，改为 `snapshot_variables(space.root)`。**执行者决策**：黑板上报用根帧起（展示全部已执行帧变量），Task 3 确认。
- server 的 `MappingResolver({})` 跨文档场景：server 单文档，跨文档 ref 会 missing_doc（现状）。`blocks_tree` 对单文档含全部命名块即可。
- `BehaviorTree.root` 现为根块树；若根块自身也 ref，其内部 RefNode 在 `_tick_ref` 动态调用。`Engine.run` 先 `enter_block(tree.name)` 建根帧，再 tick 根树。