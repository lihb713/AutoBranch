> **模块重编号**：原 **M3 schema 命名空间** 重编号为 **M2**。类型系统新增泛型 `object`。

# M3 · schema 命名空间 Spec

> 依据契约 `docs/contract.md` §5.3（变量 schema 命名空间机制）、§5.3.2（可见性规则）、§5.3.4（配置参数继承）、§5.3.5（类型契约）、§5.7.4（帧模型）、§5.10（页面变量机制）。
>
> **实现状态：已实现**（`autobranch/schema/` 包，纯逻辑无外部依赖）。实现详见 §8。

## 1. 概述

实现行为树的**变量命名空间（schema）**机制：每次文档引用产生一个独立的执行帧（命名空间，类似函数调用栈帧），管理变量的读/写、传参、返回值、配置参数继承与类型校验。**纯逻辑、无外部依赖、易测试**，是确定性信息流（§2 信息流层）的核心保障。

## 2. 功能范围

| 功能 | 说明 | 契约依据 |
|---|---|---|
| 帧模型 | 每次文档引用创建独立执行帧（schema/命名空间） | §5.7.4 |
| 严格作用域 | 每帧只读写自己的帧（裸变量名） | §5.3.2 |
| 变量读写 | `Param.xxx` 读取 / `NewParam.xxx[:类型]` 新建（ASCII 裸变量名；旧语法 `[[get]]`/`[[set]]`/`this/` 已废弃） | §5.3 |
| 传参/返回值 | 经 ref `args` 注入子文档帧、`returns` 回收子文档输出 | §5.3.2/§5.3.3 |
| 配置参数继承 | 自己的 schema → 向上找最近祖先 → 全局默认 | §5.3.4/§5.7.5 |
| 类型契约 | 创建变量时声明类型，提取错误则断言失败 | §5.3.5 |
| 页面变量机制 | 页面引用类型变量 + 操作页面绑定 | §5.10 |

## 3. 数据依赖

### 3.1 输入
- **文档接口声明**（来自 M2）：文档级 `inputs`/`outputs` 与配置参数覆盖
- **变量操作**：读取（`Param.x`）、写入（`NewParam.x[:类型]`）、配置参数查询（`resolve_config`）——ASCII 裸变量名（旧语法 `[[get]]`/`[[set]]`/`this/` 已废弃）

### 3.2 输出
- **变量值**：读取结果
- **类型校验结果**：写入/提取时校验，失败 → 断言失败（终止流程）
- **配置参数解析值**：继承规则解析后的有效值

## 4. 单元间依赖

- **依赖**：无（纯逻辑）
- **被依赖**：
  - M7（编排器）— 每次文档引用建立执行帧、变量读写
  - M5（引擎函数层）— extract 写入变量、open 写入页面引用、函数页面绑定
  - M9b（后端）— 间接通过 M7

## 5. 接口契约

### 5.1 命名空间模型

```python
class SchemaSpace:
    def enter_frame(self, name: str, decl: FrameDecl | None = None) -> SchemaFrame: ...
    # 创建子文档帧，如 T/登录/
    def exit_frame(self, frame: SchemaFrame | None = None) -> None: ...
    # 退出当前帧并恢复父帧为当前帧（帧数据保留至行为树运行结束，供黑板上报；释放=退出激活栈）
    def write(self, frame: SchemaFrame, path: str, value: Value, value_type: str) -> None: ...
    def read(self, frame: SchemaFrame, path: str) -> Value | None: ...
    # 读/写严格限定：仅自己的帧（裸变量名 单段，resolve_target 单段化）
    def set_config(self, frame: SchemaFrame, name: str, value: Value, value_type: str | None = None) -> None: ...
    # 在指定帧声明配置参数（文档覆盖全局默认用）
    def resolve_config(self, frame: SchemaFrame, name: str) -> Value: ...
    # 配置参数：自己的 schema → 祖先 → 全局默认
    def current_page(self, frame: SchemaFrame) -> PageRef | None: ...
    # 解析当前页面变量（帧中最近写入的页面引用），供 M5 绑定目标页
    def page_refs(self, frame: SchemaFrame) -> list[tuple[str, PageRef]]: ...
    # 列出帧中全部页面变量
```

- **数据契约**（`autobranch/schema/models.py`）：
  - `Value`：`str | int | float | bool | PageRef | None`
  - `PageRef`：页面引用（`page_id` + 可选 `url`）
  - `FrameDecl`：文档接口声明（`name` 文档名；`inputs`/`outputs`：变量名 → 类型；`config`/`config_types`：配置参数名 → 值/类型；来自 M2，本模块独立定义所需最小结构，避免依赖 M2 包）
  - `SchemaFrame`：独立执行帧（`id`/`name`/`parent`/`path_segments`/`storage`/`declared`/`config`/`children`/`inputs`/`outputs`/`page_write_order`），帧路径属性 `path`（如 `T/登录/`）
- **异常契约**（`autobranch/schema/errors.py`，基类 `SchemaError` 供 M7 捕获沿树传播）：
  - `SchemaPathError`：路径格式错误
  - `SchemaScopeError`：越权访问（目标帧不是自身帧）
  - `SchemaTypeError`：类型断言失败（写入/提取时值不符合声明类型，§5.3.5）

### 5.2 路径规则

- 路径为层次结构：`T/登录/username`；按 `/` 分层（`autobranch/schema/path.py`）
- 首段仅 `this`/自身文档名（自身帧）；直接子文档名不再合法 → 越权（跨帧传参经 ref `args`/`returns`）
- 目标帧后必须恰好一个变量段（变量名不含 `/`，含 `/` 或多段均被拒绝）
- 写权限：仅自己的帧
- 读权限：仅自己的帧
- 不可见：祖先、兄弟、孙子帧（越权访问 → `SchemaScopeError` 校验/运行时错误）
- 帧内变量为单段平铺存储（`storage`/`declared` 以变量名为 key）

### 5.3 可见性规则（§5.3.2）

```
每个文档执行帧只能:
  写入 → 自己的帧（裸变量名 单段）
  读取 → 自己的帧（裸变量名 单段）
  不可见 → 直接子文档 / 祖先 / 兄弟 / 孙文档 的帧（跨帧传参经 ref args/returns）
```

### 5.4 类型契约

```python
TYPE_REGISTRY = {
    "str":      TypeSpec("str", str,       lambda v: str(v)),   # 任意字符串
    "int":      TypeSpec("int", int,       _to_int),            # 真整数（排除 bool）
    "float":    TypeSpec("float", float,   _to_float),          # 数字/金额
    "bool":     TypeSpec("bool", bool,     _to_bool),           # 布尔
    "page_ref": TypeSpec("page_ref", PageRef, None),            # 页签引用，仅引擎 open() 产生
}
```

- **类型即真实存储类型**：`set` 标注驱动的 `coerce(token, raw)` 把网页 str 转成声明的 Python 类型后存储；`cast is None`（如 page_ref）拒绝文本转换，只能由引擎函数产生。
- 校验统一 `isinstance`（`autobranch/schema/types.py` 的 `check_type`），`bool` 是 `int` 子类须排除。
- 类型不匹配 / 转换失败 → `SchemaTypeError` 断言失败并终止（§5.3.5），M7 捕获基类 `SchemaError` 沿树传播。
- `validate_type_name`：未登记类型 token → 断言失败；`infer_type`：按值推断英文 token（无声明时的后备，配置参数用）。

### 5.5 配置参数继承（§5.3.4）

- 业务变量：严格作用域，不向上查找
- 配置参数（timeout/retry/...）：自己的 schema 未定义 → 最近祖先 → 全局默认
- 全局默认：工具配置文件注入根级 schema

### 5.6 页面变量（§5.10）

- 页面引用是一类变量值（`PageRef`）
- 一个 schema 可有多个页面变量
- 引擎函数绑定当前页面变量指向的页

## 6. 验收标准

- [x] 文档引用产生独立帧，同名变量互不冲突（`enter_frame` 每次创建独立帧，帧隔离测试覆盖）
- [x] 作用域规则严格：越权读/写祖先/兄弟/孙文档帧被拒绝（作用域矩阵参数化测试全组合覆盖）
- [x] 传参逐层传递正确（T→登录→输入框）
- [x] 取子文档返回值正确（经 ref `returns` 回收，非直接读子帧）
- [x] 配置参数继承正确：文档覆盖 → 祖先 → 全局默认 三级查找
- [x] 类型契约：声明类型后非法值写入/提取被拒绝（`SchemaTypeError`）
- [x] 页面变量可写入、可传递、可绑定（`current_page` 解析当前页面变量）
- [x] 纯数据结构操作，无 I/O

## 7. 测试策略

- **单元测试**：作用域规则矩阵（合法/越权读写组合）→ `tests/test_schema_scope.py`
- **继承链测试**：配置参数多级继承、文档覆盖优先级 → `tests/test_schema_config.py`
- **类型校验测试**：各类型合法/非法值 → `tests/test_schema_types.py`
- **帧隔离测试**：多文档同名变量互不干扰 → `tests/test_schema_scope.py`
- **页面变量测试**：多页面变量写入/传参/绑定 → `tests/test_schema_page.py`
- **独立性**：纯逻辑单测，无浏览器/LLM 依赖
- **集成**：端到端纯逻辑链路（登录→传参→取返回值→配置继承→断言传播→页面绑定）→ `tests/test_schema_integration.py`

## 8. 实现说明（已落地）

- **包结构**（`autobranch/schema/`，纯标准库，无外部依赖）：
  - `errors.py`：`SchemaError` 基类 + `SchemaPathError`/`SchemaScopeError`/`SchemaTypeError`
  - `models.py`：`Value`/`PageRef`/`FrameDecl`/`SchemaFrame`
  - `path.py`：`split_segments`（按 `/` 分层、拒绝空段）/`resolve_target`（提取首段目标帧 + 单段变量名）
  - `types.py`：`TYPE_REGISTRY` 类型登记表 + `TypeSpec`（token→Python 类→cast）+ `check_type`/`coerce`/`validate_type_name`/`infer_type`
  - `space.py`：`SchemaSpace` 门面（帧生命周期/读写/配置继承/页面变量）
- **严格作用域解析**（`resolve_target`）：仅 `this`/自身文档名 → 自身帧（单段化）；直接子文档名/祖先/兄弟/孙文档一律越权 → `SchemaScopeError`。目标帧后仅允许单段变量名，多段（如 `登录/输入框/值`）→ 越权。跨帧传参经 ref `args`/`returns` 进行。
- **配置继承**：`resolve_config` 沿 parent 链查找自身 `config` → 最近祖先 → 根级帧（`__init__` 注入 `global_config`）；业务变量走 `write`/`read` 严格作用域，天然不向上查找。
- **类型校验双时机**：`write` 声明类型并即时校验；`read` 提取时二次强校验（防存储被上层绕开）。
- **页面变量**：`PageRef` 为普通类型值；`current_page` 返回帧中最近写入的页面引用；`page_refs` 列出全部页面变量。
- 测试总数：63 项（M3），`pytest` 全绿、`ruff check .` 无告警。


## 8. 泛型对象类型 object（能力插件化新增，已实现）

`TYPE_REGISTRY` 新增 `object` token：**泛型对象类型**——接受任意对象值（不校验），呈现用 `str(value)`（由对象的 `__str__` 定义），用于承载插件对象（页面对象 / 会话 / 文件句柄…）；`coerce("object", v)` 原样返回，`check_type("object", v)` 恒通过。

`page_ref` 泛型化为浏览器插件的对象（`PageObject`）；引擎核心不再有 `page_ref` / 页面变量概念（页面对象作为 `object` 值在变量中存储与传递）。
