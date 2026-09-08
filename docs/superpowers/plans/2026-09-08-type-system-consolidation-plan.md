# Plan ①：类型系统收敛（TypeSpec 注册表 + isinstance + coerce + token 英文化）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 schema 类型体系从"中文名 + 自定义谓词校验"收敛为"英文 token + token↔Python 类型注册表 + isinstance 校验 + coerce 转换"，并同步所有消费点（引擎写库、parser 标注、M6 提示、测试、前端断言）。

**Architecture:** 单点替换 `schema/types.py` 的 `SUPPORTED_TYPES`（中文谓词表）为 `TYPE_REGISTRY: dict[token, TypeSpec]`（`TypeSpec(token, py_type, cast)`）。校验统一为 `isinstance`；新增 `coerce(token, raw)` 把网页提取的 str 转成真实 Python 类型。类型 token 全链路改英文：`str/int/float/bool/page_ref`。删除语义类型（金额/订单号/URL/日期等）——不占类型位。`PageRef` 保留为唯一自定义类型（`cast=None`，只能由引擎函数产生）。此 plan **不**改 DSL 块语法、不改 `{{ }}` 括号（留 Plan ②）。

**Tech Stack:** Python 3.11, dataclass, pytest。

**Spec:** `docs/superpowers/specs/2026-09-08-block-function-call-design.md`（§2 类型系统、§6 模块影响）

## Global Constraints

- 全程中文（对话与文档），但代码标识符/DSL token 用英文。
- conda 环境 `webops`（`conda run -n webops --no-capture-output python -m pytest ...`）。
- 每任务 TDD：先写失败测试→运行确认失败→实现→运行确认通过。
- 类型 token 唯一来源 `TYPE_REGISTRY` 的键：`str` / `int` / `float` / `bool` / `page_ref`。
- 不得保留对中文类型名（`文本`/`整数`/`金额`/`订单号`/`URL`/`日期`/`布尔`/`数字`/`页面引用`）的引用，除了**历史 spec/设计文档**（那些是文档，不改）。
- `PageRef`（页签引用）不可由文本 coerce；`open()` 是唯一合法产生途径。
- `bool` 是 `int` 子类：`int` 校验须排除 bool（`isinstance(v, int) and not isinstance(v, bool)`）。

---

### Task 1: 重构 schema/types.py 为 TypeSpec 注册表

**Files:**
- Modify: `webops/schema/types.py`（全文重写）
- Test: `tests/test_schema_types.py`（新建/覆盖）— 注意此文件名已存在且是旧中文类型测试，需重写

**Interfaces:**
- Consumes: `webops/schema/models.py` 的 `PageRef`, `Value`
- Produces:
  - `TypeSpec` dataclass: `token: str`, `py_type: type`, `cast: Callable | None`
  - `TYPE_REGISTRY: dict[str, TypeSpec]`（键 = `str/int/float/bool/page_ref`）
  - `validate_type_name(token) -> None`（未登记抛 `SchemaTypeError`）
  - `check_type(token, value) -> None`（isinstance 校验，不匹配抛 `SchemaTypeError`）
  - `coerce(token, raw) -> Value`（`cast is None` 时抛 `SchemaTypeError`）
  - `infer_type(value) -> str`（返回英文 token：bool→bool, int→int, float→float, PageRef→page_ref, 其余→str）

- [ ] **Step 1: 写失败测试 `tests/test_schema_types.py`**

覆盖核心行为（先删旧文件重写）：

```python
"""类型系统收敛测试：TypeSpec 注册表 + isinstance 校验 + coerce。"""
import pytest

from webops.schema.errors import SchemaTypeError
from webops.schema.models import PageRef
from webops.schema.types import (
    TYPE_REGISTRY,
    check_type,
    coerce,
    infer_type,
    validate_type_name,
)


def test_registry_has_english_tokens():
    assert set(TYPE_REGISTRY) == {"str", "int", "float", "bool", "page_ref"}


def test_py_types_mapped():
    assert TYPE_REGISTRY["str"].py_type is str
    assert TYPE_REGISTRY["int"].py_type is int
    assert TYPE_REGISTRY["float"].py_type is float
    assert TYPE_REGISTRY["bool"].py_type is bool
    assert TYPE_REGISTRY["page_ref"].py_type is PageRef


def test_validate_unknown_token_raises():
    with pytest.raises(SchemaTypeError):
        validate_type_name("文本")  # 中文名不再登记


@pytest.mark.parametrize(
    ("token", "good", "bad"),
    [
        ("str", "abc", 5),
        ("int", 5, "abc"),
        ("float", 1.5, "abc"),
        ("bool", True, 1),
    ],
)
def test_check_type_isinstance(token, good, bad):
    check_type(token, good)
    with pytest.raises(SchemaTypeError):
        check_type(token, bad)


def test_int_excludes_bool():
    with pytest.raises(SchemaTypeError):
        check_type("int", True)  # bool 是 int 子类，须排除


def test_page_ref_checked_by_isinstance():
    pr = PageRef(page_id="1")
    check_type("page_ref", pr)
    with pytest.raises(SchemaTypeError):
        check_type("page_ref", "http://x")  # 字符串不是页签引用


def test_coerce_basic():
    assert coerce("int", "123") == 123
    assert coerce("float", "1.5") == 1.5
    assert coerce("bool", "true") is True
    assert coerce("str", 123) == "123"


@pytest.mark.parametrize("raw", ["abc", "", "1.5x"])
def test_coerce_int_failure(raw):
    with pytest.raises(SchemaTypeError):
        coerce("int", raw)


def test_coerce_page_ref_rejected():
    with pytest.raises(SchemaTypeError):
        coerce("page_ref", "http://x")  # 页签引用不能由文本产生


def test_infer_type_english():
    assert infer_type(True) == "bool"
    assert infer_type(5) == "int"
    assert infer_type(1.5) == "float"
    assert infer_type(PageRef(page_id="1")) == "page_ref"
    assert infer_type("abc") == "str"
```

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n webops --no-capture-output python -m pytest tests/test_schema_types.py -q`
Expected: FAIL（`SUPPORTED_TYPES` 不存在、import 错误等）

- [ ] **Step 3: 重写 `webops/schema/types.py`**

```python
"""M3 schema 命名空间：类型契约（契约 §5.3.5，收敛版）。

``TYPE_REGISTRY`` 把 DSL token 映射到**真实 Python 类型**，校验统一
``isinstance``；``coerce`` 把网页提取的 str 转成目标真实类型。类型即
存储类型——声明 ``int`` 的变量存的就是 Python ``int``。

自定义类型扩展 = 注册表加一行（token + Python 类 + 可选 cast）。当前
唯一自定义类型是 ``page_ref``（页签引用，无 cast，只能由引擎 open()
产生）。校验失败触发 ``SchemaTypeError``（断言失败语义），由 M7 捕获。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from webops.schema.errors import SchemaTypeError
from webops.schema.models import PageRef, Value


@dataclass(frozen=True)
class TypeSpec:
    """类型注册项：DSL token → 真实 Python 类型 + 可选 cast。

    :param token: DSL 引用名（str/int/float/bool/page_ref）。
    :param py_type: 真实 Python 类型（isinstance 校验目标）。
    :param cast: 网页 str → 该类型的转换；None = 不可由文本产生
      （如 page_ref，只能由引擎函数生成）。
    """

    token: str
    py_type: type
    cast: Callable[[Value], Value] | None = None


def _to_int(value: Value) -> int:
    if isinstance(value, bool):
        raise SchemaTypeError(f"不能把布尔转成整数: {value!r}")
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise SchemaTypeError(f"无法转成 int: {value!r}") from exc


def _to_float(value: Value) -> float:
    if isinstance(value, bool):
        raise SchemaTypeError(f"不能把布尔转成浮点: {value!r}")
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise SchemaTypeError(f"无法转成 float: {value!r}") from exc


def _to_bool(value: Value) -> bool:
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off", ""):
        return False
    raise SchemaTypeError(f"无法转成 bool: {value!r}")


TYPE_REGISTRY: dict[str, TypeSpec] = {
    "str": TypeSpec("str", str, lambda v: str(v)),
    "int": TypeSpec("int", int, _to_int),
    "float": TypeSpec("float", float, _to_float),
    "bool": TypeSpec("bool", bool, _to_bool),
    "page_ref": TypeSpec("page_ref", PageRef, None),
}


def validate_type_name(token: str) -> None:
    if token not in TYPE_REGISTRY:
        raise SchemaTypeError(
            f"不支持的变量类型: {token!r}（支持: {sorted(TYPE_REGISTRY)}）"
        )


def check_type(token: str, value: Value) -> None:
    """强校验值是否是该 token 对应 Python 类型的实例（契约 §5.3.5）。"""
    spec = TYPE_REGISTRY.get(token)
    if spec is None:
        raise SchemaTypeError(f"不支持的变量类型: {token!r}")
    if token == "int" and isinstance(value, bool):
        raise SchemaTypeError(f"类型断言失败: 值 {value!r} 不符合类型 'int'（排除布尔）")
    if not isinstance(value, spec.py_type):
        raise SchemaTypeError(f"类型断言失败: 值 {value!r} 不符合类型 {token!r}")


def coerce(token: str, raw: Value) -> Value:
    """按 token 把值转成真实存储类型（set 标注驱动；网页值→Python 类型）。

    ``cast is None``（如 page_ref）拒绝文本转换——只能由引擎函数产生。
    """
    spec = TYPE_REGISTRY.get(token)
    if spec is None:
        raise SchemaTypeError(f"不支持的变量类型: {token!r}")
    if isinstance(raw, spec.py_type) and token != "int":
        return raw
    if spec.cast is None:
        raise SchemaTypeError(
            f"类型 {token!r} 不能由值 {raw!r} 转换，只能由引擎函数产生"
        )
    if token == "int" and isinstance(raw, spec.py_type) and isinstance(raw, bool):
        raise SchemaTypeError(f"不能把布尔存成 int: {raw!r}")
    return spec.cast(raw)


def infer_type(value: Value) -> str:
    """按 Python 值类型推断 token（用于缺省声明类型）。"""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, PageRef):
        return "page_ref"
    return "str"
```

> 说明：`coerce` 中"已是目标类型则原样返回"保证幂等（避免 str 已注入后再转义）；`page_ref` 无 cast 故任何文本都拒绝；`int` 特判排除 bool（含已是 bool 时直接抛错）。

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n webops --no-capture-output python -m pytest tests/test_schema_types.py -q`
Expected: PASS（全绿）

- [ ] **Step 5: 更新 schema/__init__.py 导出**

`webops/schema/__init__.py` 目前导出 `SUPPORTED_TYPES`。改为导出新符号（供各模块 import）。先确认当前导出清单再改：

Run: `conda run -n webops --no-capture-output python -c "import webops.schema as s; print(s.__all__)"`
Expected: 输出包含 `SUPPORTED_TYPES` 等

把 `SUPPORTED_TYPES` 从导出替换为 `TYPE_REGISTRY`（保留 `check_type/infer_type/validate_type_name` 导出）。若 `SUPPORTED_TYPES` 仍被别处 import，见 Task 2/3 一并清理。

- [ ] **Step 6: Commit**

```bash
git add webops/schema/types.py webops/schema/__init__.py tests/test_schema_types.py
git commit -m "refactor(schema): type registry with isinstance+coerce, english tokens"
```

---

### Task 2: 迁移 schema 层测试到英文 token

**Files:**
- Modify: `tests/test_schema_models.py`、`tests/test_schema_blackboard.py`、`tests/test_schema_integration.py`、`tests/test_schema_config.py`、`tests/test_schema_scope.py`、`tests/test_schema_page.py`（及运行发现的其余 `tests/test_schema*.py`）
- Test: `tests/test_schema*.py`（tests-only；`webops/` 源码不改——space.py 仅透传 token 无需迁移，engine/parser/prompts 消费点归 Task 3）

**Interfaces:**
- Consumes: `SchemaSpace.write/read/set_config`（不变，类型名实参改英文）、`PageRef`
- Produces: 无新接口。所有 schema 层测试类型实参从中文改英文。

- [ ] **Step 1: grep 全部 schema 层测试里的中文类型名**

Run: `rg -n '"文本"|"整数"|"数字"|"布尔"|"金额"|"订单号"|"URL"|"日期"|"页面引用"' tests/test_schema*.py`
Expected: 列出所有出现行（这些都要改成对应英文 token：文本→str、整数→int、数字→float、布尔→bool、金额→float、订单号→str、URL→str、日期→str、页面引用→page_ref）

> 语义类型（金额/订单号/URL/日期）本质是基础类型：映射到 `float`/`str`。设计决策：这些"业务语义"不占类型位。

- [ ] **Step 2: 迁移每个出现点（用精确替换）**

按上表把 `tests/test_schema_*.py` 里的中文类型名字符串字面量改成英文 token。特别：
- `tests/test_schema_models.py:98-101`（`test_supported_types_enumerable`）→ 断言 `{"str","int","float","bool","page_ref"}`；`test_validate_type_name`（128-132）改 `validate_type_name("str")` + `"未知类型"` 抛错；`test_infer_type`（140-146）改 `infer_type(True)=="bool"` 等。
- `tests/test_schema_blackboard.py:65-76`：`type == "金额"`→`"float"`、`"文本"`→`"str"`、`"页面引用"`→`"page_ref"`。
- `tests/test_schema_integration.py:30-31`：`inputs={"username": "文本",...}`→`"str"`；`outputs={"login_success": "布尔"}`→`"bool"`。
- 若原测试还覆盖"金额/订单号/URL/日期"写值行为，改为对应基础类型（float/str），值如 `"98.00"` 配 `float`。

- [ ] **Step 3: 运行 schema 测试确认**

Run: `conda run -n webops --no-capture-output python -m pytest tests/test_schema_types.py tests/test_schema_models.py tests/test_schema_blackboard.py tests/test_schema_integration.py -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_schema_types.py tests/test_schema_models.py tests/test_schema_blackboard.py tests/test_schema_integration.py
git commit -m "test(schema): migrate type names to english tokens"
```

---

### Task 3: 迁移 M5 引擎写库类型 + M6 提示到英文 token

**Files:**
- Modify: `webops/engine/engine.py:178,238,402`（`"页面引用"`→`"page_ref"`、`"文本"`→`"str"`）
- Modify: `webops/engine/tools.py:34,36,61`（工具描述里 `{{set:page:xxx}}`/`{{set:string:xxx}}` 文案 → `page_ref`/`str`）
- Modify: `webops/leaf_agent/executor.py`（若 set_decls 类型被比较则同步，见 grep）
- Modify: `webops/leaf_agent/prompts.py:98-103`（`"page"`→`"page_ref"`、`"string"`→`"str"`）
- Modify: `webops/parser/expand.py:42-44`（`_SET_TMPL` 正则 `page|string` → 接受通用 token）+ `webops/parser/models.py:85-87`（set_decls 注释）
- Test: `tests/test_parser_vars.py`、`tests/engine/test_engine.py`、`tests/leaf_agent/test_get_replace.py`、`tests/orchestrator/*`

**Interfaces:**
- Consumes: `TYPE_REGISTRY` 键（str/int/float/bool/page_ref）
- Produces:
  - M5 `open` 写库类型 `"page_ref"`；`get_url` 写库类型 `"str"`；`extract` 缺省 `infer_type` 已是英文
  - parser `{{set:<token>:path}}` 正则允许 `[a-z_]+`（通用英文 token）
  - `set_decls` type 值 = `page_ref`/`str`/`int`/`float`/`bool` 等

> 注意：此任务把 set 标注 token 从 `page`/`string` 改为注册表 token（`page_ref`/`str`）。这样"set 标注类型"与"引擎产物类型"是**同一套** token（统一的关键一步）。

- [ ] **Step 1: 改 parser 正则与注释**

`webops/parser/expand.py:42-45`：
```python
#: ``{{set[:type]:path}}`` 写入声明；type ∈ TYPE_REGISTRY token（可省略）
#: path 可带 this/ 或不带
_SET_TMPL = re.compile(
    r"\{\{\s*set:(?:(str|int|float|bool|page_ref):)?\s*((?:this/)?[^{}:]+?)\s*\}\}"
)
```

`webops/parser/models.py:84-87` 注释同步（`page_ref` 存页签引用、`str` 存文本）。

- [ ] **Step 2: 改 M5 引擎硬编码类型 + extract 写库 coerce**

- `webops/engine/engine.py:178`: `"页面引用"` → `"page_ref"`
- `webops/engine/engine.py:238`: `"文本"` → `"str"`
- `webops/engine/engine.py` `extract`（389-417）：改 `type_name = self._declared_type(frame, target) or infer_type(value)` 处，使**声明了类型就 coerce**：

```python
type_name = self._declared_type(frame, target)
if type_name is None:
    type_name = infer_type(value)   # 无声明 → 按值推断（网页值即 str）
else:
    try:
        value = coerce(type_name, value)   # 有声明 → 转成真实存储类型
    except SchemaTypeError as exc:
        return OpResult(
            False,
            f"提取值无法转换为类型 {type_name}: {exc}",
            {"code": ErrorCode.INVALID_ARGUMENT, "var": target, "type": type_name},
        )
```

并在 import 行加 `coerce`：`from webops.schema.types import coerce, infer_type`。

确认无其他中文类型名字符串：
Run: `rg -n '"页面引用"|"文本"|"整数"|"布尔"' webops/engine webops/leaf_agent`
Expected: 无输出（全清）

- [ ] **Step 3: 改 M6 prompts 与工具描述**

`webops/leaf_agent/prompts.py:98-103`：
```python
if type_name == "page_ref":
    hints.append(f"{target}（页签：打开页面后调 open 的 save_to 存入）")
elif type_name == "str":
    hints.append(f"{target}（文本：调 extract 或 get_url 存入）")
else:
    hints.append(f"{target}（{type_name}：提取并转换后存入）")
```

`webops/engine/tools.py:34,36,61`：`{{set:page:xxx}}`→`{{set:page_ref:xxx}}`、`{{set:string:xxx}}`→`{{set:str:xxx}}`。

- [ ] **Step 4: 迁移受影响测试的类型 token**

- `tests/test_parser_vars.py:82-125`：`{{set:page:页面A}}` → `{{set:page_ref:页面A}}`，断言 `set_decls == (("this/页面A","page_ref"),)`；`{{set:string:url}}`→`{{set:str:url}}`，断言 `"str"`。
- `tests/leaf_agent/test_get_replace.py:211-255`：`set_decls` 里 `"page"`→`"page_ref"`；47/90 行 `space.write(...,"金额"/"文本")` → `"float"/"str"`（值为浮点/字符串匹配）；160 行 detail `"type":"文本"`→`"str"`。
- `tests/engine/test_engine.py:80-89,219,228,334-343`：`frame.outputs={"订单号":"订单号"}`→`{"订单号":"str"}` 语义需注意——订单号本质是 str，值 "ORD-001" 配 "str"；`{"数量":"整数"}`→`{"数量":"int"}`；`get_url` 后 `frame.declared.get("url文本")=="文本"`→`=="str"`。
- `tests/engine/test_engine.py` 其他写库 `"页面引用"`→`"page_ref"`。
- `tests/orchestrator/test_schema_frames.py:73`：`"文本"`→`"str"`。
- `tests/orchestrator/test_engine_integration.py:185-190`：`"页面引用"`→`"page_ref"`。

- [ ] **Step 5: 运行受影响测试**

Run: `conda run -n webops --no-capture-output python -m pytest tests/test_parser_vars.py tests/engine/test_engine.py tests/leaf_agent/test_get_replace.py tests/orchestrator -q`
Expected: PASS。若失败是因 extract 类型校验语义（订单号校验谓词曾拒绝含空格；现在纯 str 校验更宽松），按新语义调整测试值。

- [ ] **Step 6: Commit**

```bash
git add webops/parser/expand.py webops/parser/models.py webops/engine/engine.py webops/engine/tools.py webops/leaf_agent/prompts.py tests/
git commit -m "refactor(types): unify set-annotation and engine-stored tokens to registry tokens"
```

---

### Task 4: 迁移前端黑板断言 + 全量回归

**Files:**
- Modify: `webops/frontend/src/features/reports/BlackboardPanel.test.tsx`（12-34 行 type 断言：`"文本"`→`"str"`、`"金额"`→`"float"`、`"页面引用"`→`"page_ref"`）
- Modify（如存在）: `webops/frontend/src/features/reports/BlackboardPanel.tsx` 无改动（type 纯透传）
- Test: 全量

**Interfaces:**
- Consumes: 后端变量 type 已英文
- Produces: 无

- [ ] **Step 1: 迁移前端测试断言**

Run: `rg -n '"文本"|"金额"|"页面引用"|"整数"' webops/frontend/src --glob '*.ts*'`
Expected: 列出 BlackboardPanel.test.tsx 等。将中文类型断言改英文 token。

- [ ] **Step 2: 运行前端测试**

Run: `npm.cmd test -- --run` （在 `webops/frontend`）
Expected: PASS（71 附近）

- [ ] **Step 3: 全量后端回归**

Run: `conda run -n webops --no-capture-output python -m pytest -q`
Expected: PASS（原 769+，仅语义类型相关用例按新映射调整）

- [ ] **Step 4: 清理残留中文 token 引用（生产代码）**

Run: `rg -n '"文本"|"整数"|"金额"|"订单号"|"URL"|"日期"|"布尔"|"数字"|"页面引用"' webops/`
Expected: 无输出（排除 docstring 中说明历史/文档引用可保留，但要确认无代码逻辑引用）

- [ ] **Step 5: lint + typecheck**

Run（backend）: `conda run -n webops --no-capture-output python -m ruff check webops tests`
Run（frontend, `webops/frontend`）: `npm.cmd run lint; npm.cmd run typecheck`
Expected: 全绿

- [ ] **Step 6: 文档同步（代码相关部分）**

- 更新 `webops/schema/types.py` 模块 docstring 已含（Task 1）。
- `webops/leaf_agent/prompts.py` PROMPT_VERSION 提到新提示则 bump 到 `1.4`。
- spec 文档 `docs/superpowers/specs/2026-09-08-*.md` 无需改（已是目标态）。
- 若契约 `docs/contract.md` §5.3.5 类型表描述旧中文类型，记录到"待 Plan ②/③ 后统一文档同步"清单（本 plan 不展开契约大改）。

- [ ] **Step 7: Commit**

```bash
git add webops/frontend/src webops/leaf_agent/prompts.py
git commit -m "test+docs: english type tokens end to end"
```

---

## Self-Review 记录

**Spec 覆盖**：spec §2（TYPE_REGISTRY/isinstance/coerce/page_ref 无文本 cast/bool 排除）→ Task 1；§6 M5/M6/parser 消费点 → Task 3；快照/黑板 type 透传 → Task 4。**未覆盖**：spec 里 set 标注驱动的 coerce 落地到"块 inputs 传参"——依赖 Plan ②/③ 的 inputs dict，明确排除于本 plan。

**Placeholder 扫描**：无 TBD。Step 级 grep 命令给出精确模式。

**类型一致性**：`TYPE_REGISTRY` 键 = str/int/float/bool/page_ref，全文统一；`infer_type`/`coerce`/`check_type` 签名一致。

**注意（执行者）**：Task 3 中 extract 已按新语义实现"声明了类型就 coerce"（Step 2 含代码），语义类型校验谓词（订单号/金额）删除是设计意图（不占类型位）而非回归。原依赖"声明整数却提取 'abc' 报错"的测试保持报错（coerce 抛 SchemaTypeError）；原"声明浮点提取 '98.00' 成功"测试现在因 coerce 成功（98.0）。若实测原测试值含空格/前缀，按 coerce 结果微调测试值即可。
