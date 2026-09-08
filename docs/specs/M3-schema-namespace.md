# M3 · schema 命名空间 Spec

> 依据契约 `docs/contract.md` §5.3（变量 schema 命名空间机制）、§5.3.2（可见性规则）、§5.3.4（配置参数继承）、§5.3.5（类型契约）、§5.7.4（帧模型）、§5.10（页面变量机制）。
>
> **实现状态：已实现**（`webops/schema/` 包，纯逻辑无外部依赖）。实现详见 §8。

## 1. 概述

实现行为树的**变量命名空间（schema）**机制：每个块实例拥有独立的命名空间（类似函数调用栈帧），管理变量的读/写、传参、返回值、配置参数继承与类型校验。**纯逻辑、无外部依赖、易测试**，是确定性信息流（§2 信息流层）的核心保障。

## 2. 功能范围

| 功能 | 说明 | 契约依据 |
|---|---|---|
| 帧模型 | 每次块引用创建独立 schema（命名空间） | §5.7.4 |
| 严格作用域 | 每块只读写自己的 schema + 直接子块的 schema | §5.3.2 |
| 变量读写 | 路径形式读写（`$this/xxx`、`{{$this/xxx}}`） | §5.3 |
| 传参/返回值 | 父块写直接子块 schema；读直接子块 schema 取返回值 | §5.3.2/§5.3.3 |
| 配置参数继承 | 自己的 schema → 向上找最近祖先 → 全局默认 | §5.3.4/§5.7.5 |
| 类型契约 | 创建变量时声明类型，提取错误则断言失败 | §5.3.5 |
| 页面变量机制 | 页面引用类型变量 + 操作页面绑定 | §5.10 |

## 3. 数据依赖

### 3.1 输入
- **块声明**（来自 M2）：命名块的输入/输出/配置参数声明
- **变量操作**：写入（`=> $this/path`）、读取（`{{$this/path}}`）、配置参数查询

### 3.2 输出
- **变量值**：读取结果
- **类型校验结果**：写入/提取时校验，失败 → 断言失败（终止流程）
- **配置参数解析值**：继承规则解析后的有效值

## 4. 单元间依赖

- **依赖**：无（纯逻辑）
- **被依赖**：
  - M7（编排器）— 每次块引用建立 schema 帧、变量读写
  - M5（引擎函数层）— extract 写入变量、open 写入页面引用、函数页面绑定
  - M9b（后端）— 间接通过 M7

## 5. 接口契约

### 5.1 命名空间模型

```python
class SchemaSpace:
    def enter_block(self, block_name: str, decl: BlockDecl) -> SchemaFrame: ...
    # 创建子块帧，如 T/登录/
    def exit_block(self, frame: SchemaFrame | None = None) -> None: ...
    # 退出当前帧并恢复父帧为当前帧（帧数据保留，供父块读返回值）
    def write(self, frame: SchemaFrame, path: str, value: Value, value_type: str) -> None: ...
    def read(self, frame: SchemaFrame, path: str) -> Value | None: ...
    # 读/写严格限定：自己的帧 + 直接子帧
    def set_config(self, frame: SchemaFrame, name: str, value: Value, value_type: str | None = None) -> None: ...
    # 在指定帧声明配置参数（块覆盖全局默认用）
    def resolve_config(self, frame: SchemaFrame, name: str) -> Value: ...
    # 配置参数：自己的 schema → 祖先 → 全局默认
    def current_page(self, frame: SchemaFrame) -> PageRef | None: ...
    # 解析当前页面变量（帧中最近写入的页面引用），供 M5 绑定目标页
    def page_refs(self, frame: SchemaFrame) -> list[tuple[str, PageRef]]: ...
    # 列出帧中全部页面变量
```

- **数据契约**（`webops/schema/models.py`）：
  - `Value`：`str | int | float | bool | PageRef | None`
  - `PageRef`：页面引用（`page_id` + 可选 `url`）
  - `BlockDecl`：块接口声明（`inputs`/`outputs`：变量名 → 类型；`config`/`config_types`：配置参数名 → 值/类型；来自 M2，本模块独立定义所需最小结构，避免依赖 M2 包）
  - `SchemaFrame`：独立帧（`id`/`block_name`/`parent`/`path_segments`/`storage`/`declared`/`config`/`children`/`inputs`/`outputs`/`page_write_order`），帧路径属性 `path`（如 `T/登录/`）
- **异常契约**（`webops/schema/errors.py`，基类 `SchemaError` 供 M7 捕获沿树传播）：
  - `SchemaPathError`：路径格式错误
  - `SchemaScopeError`：越权访问（目标帧不是自身或直接子帧）
  - `SchemaTypeError`：类型断言失败（写入/提取时值不符合声明类型，§5.3.5）

### 5.2 路径规则

- 路径为层次结构：`T/登录/username`；按 `/` 分层（`webops/schema/path.py`）
- 首段标识目标帧：`$this` 或自身块名（自身帧）、直接子块名（直接子帧）；其余 → 越权
- 目标帧后必须恰好一个变量段（变量名不含 `/`，含 `/` 或多段均被拒绝）
- 写权限：自己的帧 + 直接子帧
- 读权限：自己的帧 + 直接子帧
- 不可见：祖先、兄弟、孙子帧（越权访问 → `SchemaScopeError` 校验/运行时错误）
- 帧内变量为单段平铺存储（`storage`/`declared` 以变量名为 key）

### 5.3 可见性规则（§5.3.2）

```
每块实例只能:
  写入 → 自己的 schema + 直接子块的 schema
  读取 → 自己的 schema + 直接子块的 schema
  不可见 → 祖先、兄弟、孙子 的 schema
```

### 5.4 类型契约

```python
SUPPORTED_TYPES = {
    "金额":  值必须为数字（int/float 或纯数字字符串，拒绝 bool/含货币符号文本）,
    "订单号": 非空且不含空白的字符串,
    "URL":   http:// 或 https:// 开头的字符串,
    "日期":  date/datetime 或 "YYYY-MM-DD" 字符串,
    "文本":  任意字符串,
    "页面引用": PageRef 实例,
    "布尔":  bool 实例,
    "整数":  int（不含 bool）,
    "数字":  int/float（不含 bool）,
}
```

- 写入时声明类型，读取/提取时强校验（`webops/schema/types.py` 的 `check_type`）
- 类型不匹配 → `SchemaTypeError` 断言失败并终止（§5.3.5），M7 捕获基类 `SchemaError` 沿树传播
- `validate_type_name`：未登记类型名 → 断言失败；`infer_type`：按值推断缺省类型（配置参数用）

### 5.5 配置参数继承（§5.3.4）

- 业务变量：严格作用域，不向上查找
- 配置参数（timeout/retry/...）：自己的 schema 未定义 → 最近祖先 → 全局默认
- 全局默认：工具配置文件注入根级 schema

### 5.6 页面变量（§5.10）

- 页面引用是一类变量值（`PageRef`）
- 一个 schema 可有多个页面变量
- 引擎函数绑定当前页面变量指向的页

## 6. 验收标准

- [x] 块引用产生独立帧，同名变量互不冲突（`enter_block` 每次创建独立帧，帧隔离测试覆盖）
- [x] 作用域规则严格：越权读/写祖先/兄弟/孙子帧被拒绝（作用域矩阵参数化测试全组合覆盖）
- [x] 传参逐层传递正确（T→登录→输入框）
- [x] 取子块返回值正确（读直接子帧）
- [x] 配置参数继承正确：块覆盖 → 祖先 → 全局默认 三级查找
- [x] 类型契约：声明类型后非法值写入/提取被拒绝（`SchemaTypeError`）
- [x] 页面变量可写入、可传递、可绑定（`current_page` 解析当前页面变量）
- [x] 纯数据结构操作，无 I/O

## 7. 测试策略

- **单元测试**：作用域规则矩阵（合法/越权读写组合）→ `tests/test_schema_scope.py`
- **继承链测试**：配置参数多级继承、块覆盖优先级 → `tests/test_schema_config.py`
- **类型校验测试**：各类型合法/非法值 → `tests/test_schema_types.py`
- **帧隔离测试**：多块同名变量互不干扰 → `tests/test_schema_scope.py`
- **页面变量测试**：多页面变量写入/传参/绑定 → `tests/test_schema_page.py`
- **独立性**：纯逻辑单测，无浏览器/LLM 依赖
- **集成**：端到端纯逻辑链路（登录→传参→取返回值→配置继承→断言传播→页面绑定）→ `tests/test_schema_integration.py`

## 8. 实现说明（已落地）

- **包结构**（`webops/schema/`，纯标准库，无外部依赖）：
  - `errors.py`：`SchemaError` 基类 + `SchemaPathError`/`SchemaScopeError`/`SchemaTypeError`
  - `models.py`：`Value`/`PageRef`/`BlockDecl`/`SchemaFrame`
  - `path.py`：`split_segments`（按 `/` 分层、拒绝空段）/`resolve_target`（提取首段目标帧 + 单段变量名）
  - `types.py`：`SUPPORTED_TYPES` 类型登记表 + `check_type`/`validate_type_name`/`infer_type`
  - `space.py`：`SchemaSpace` 门面（帧生命周期/读写/配置继承/页面变量）
- **严格作用域解析**（`resolve_target`）：首段为 `$this`/自身块名 → 自身帧；首段为直接子块名 → 直接子帧；其余 → `SchemaScopeError`。目标帧后仅允许单段变量名，多段（如 `$this/登录/输入框/值`）→ 越权。
- **配置继承**：`resolve_config` 沿 parent 链查找自身 `config` → 最近祖先 → 根级帧（`__init__` 注入 `global_config`）；业务变量走 `write`/`read` 严格作用域，天然不向上查找。
- **类型校验双时机**：`write` 声明类型并即时校验；`read` 提取时二次强校验（防存储被上层绕开）。
- **页面变量**：`PageRef` 为普通类型值；`current_page` 返回帧中最近写入的页面引用；`page_refs` 列出全部页面变量。
- 测试总数：63 项（M3），`pytest` 全绿、`ruff check .` 无告警。