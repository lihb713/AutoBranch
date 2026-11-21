# AutoBranch 插件开发指南

> 本文面向想扩展 AutoBranch 能力的开发者。建议先阅读 [行为树指南](behavior-tree-guide.md) 了解 `FunctionCall`、`Param`、`NewParam` 和报告。
>
> 相关文档：
> - [行为树指南](behavior-tree-guide.md)
> - [内置插件介绍](builtin-plugins.md)
> - [完整用户手册](user-guide.md)

## 1. 插件是什么

插件是一组可被行为树调用的能力：

- 向 `FunctionCall` 提供确定性函数；
- 向 LLM 叶子提供工具（`use_capability` 后进入工具集）；
- 可以声明自己的**自定义类型**；
- 可选提供配置、REST API、数据库模型、前端页面、存储目录。

插件只负责**返回值**，不直接操作变量空间。变量写入由引擎根据 `save_to` / `returns` / `NewParam` 落笔。

## 2. 插件放在哪里

### 2.1 预置插件

位于 `autobranch/plugins/<插件名>/`，随项目启动加载。

### 2.2 用户自定义插件

在管理系统的「插件管理」页编写源码，源码保存在数据库；保存时会做：

1. Python 语法检查；
2. 仅标准库检查；
3. 试加载；
4. 注册函数与自定义类型。

自定义插件源码必须定义模块变量：

```python
plugin = MyPlugin()
```

## 3. 最小插件

```python
class MyPlugin(PluginBase):
    name = "my_plugin"
    description = "我的演示插件"

    @engine_function(
        name="double",
        description="把数字乘以 2",
        parameters={
            "type": "object",
            "properties": {
                "x": {"type": "number", "description": "输入数字"},
            },
            "required": ["x"],
        },
        returns={"result": "float"},
    )
    def double(self, x: float) -> float:
        return x * 2


plugin = MyPlugin()
```

保存后可在 FunctionCall 中调用：

```yaml
n2:
  type: FunctionCall
  function: my_plugin.double
  args: ["3"]
  returns: {result: float}
```

## 4. 插件类与函数注册

### 4.1 `PluginBase`

插件必须继承 `PluginBase`，至少设置：

```python
name = "my_plugin"
description = "能力说明"
```

可选实现：

| 属性/方法 | 用途 |
|---|---|
| `function_defs()` | 框架自动收集装饰器函数，通常不用重写 |
| `init(runtime)` | 首次被使用时初始化资源 |
| `release()` | 运行结束释放资源 |
| `custom_types` | 声明插件自定义类型 |
| `config_schema` | 插件配置表单 schema |
| `get_config()` / `set_config()` | 读写插件配置 |
| `frontend_manifest` | 声明前端页面入口 |
| `storage_dir` | 插件存储目录 |
| `register_routes(app)` | 注册插件 REST API |
| `register_models(base)` | 注册数据库模型 |

### 4.2 `@engine_function`

用户与 LLM 均可见：

- 进入 LLM 工具集；
- 出现在 `GET /api/functions`；
- 可被 `FunctionCall` 直接调用。

### 4.3 `@llm_function`

仅 LLM 可见：

- 进入 LLM 工具集；
- **不可**被 FunctionCall 引用；
- 不出现在用户函数清单。

适合语义图、页面内部操作等需要 LLM 根据上下文调用的技术接口。

### 4.4 函数名

函数以全名标识：

```text
插件名.函数名
```

例如：

```text
compute.add
ssh.ssh_exec
my_plugin.double
```

同一插件内函数名必须唯一；不同插件可以同名。

## 5. 函数参数

`parameters` 使用 JSON Schema：

```python
parameters={
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "请求地址"},
        "timeout": {"type": "number", "description": "超时秒数"},
        "headers": {"type": "object", "description": "请求头"},
        "items": {"type": "array", "items": {}, "description": "列表"},
    },
    "required": ["url"],
}
```

常用类型：

| JSON Schema type | 前端显示 | Python 值 |
|---|---|---|
| `string` | `str` | `str` |
| `integer` | `int` | `int` |
| `number` | `float` | `int/float` |
| `boolean` | `bool` | `bool` |
| `array` | `array` | `list` |
| `object` | `object` | `dict` |
| 不写 `type` | `generics` | 任意值 |

> 自定义类型主要用于**函数返回类型**和**行为树接口类型**。如果参数是插件内部对象，建议用描述说明，不要依赖 JSON Schema 的自定义 type。

## 6. 返回值与类型

### 6.1 `returns`

```python
returns={"result": "float", "count": "int"}
```

`returns` 的键是返回参数名，值必须是合法类型 token：

- 核心：`str` / `int` / `float` / `bool` / `array` / `object` / `generics` / `page_ref`
- 本插件通过 `custom_types` 注册的自定义类型。

选择原则：

| 返回值 | 推荐类型 |
|---|---|
| 字符串 | `str` |
| 整数 | `int` |
| 数字 | `float` |
| 布尔 | `bool` |
| Python list | `array` |
| Python dict | `object` |
| 页面对象 / 会话 / 文件句柄 | 自定义类型（如 `page_object` / `ssh_session`） |
| 确实无法归类 | `generics` |

不要把所有对象都用 `object`：`object` 在 AutoBranch 中表示 Python `dict`。

### 6.2 返回裸值

```python
@engine_function(name="add", returns={"result": "float"})
def add(self, a: float, b: float) -> float:
    return a + b
```

### 6.3 返回 `FunctionResult`

需要失败原因、报告附加信息或多返回值时：

```python
@engine_function(name="read", returns={"content": "str"})
def read(self, path: str) -> FunctionResult:
    try:
        return FunctionResult.success("hello")
    except Exception as exc:
        return FunctionResult.failure(f"读取失败: {exc}", code="READ_ERROR")
```

```python
FunctionResult.success(
    "value1",
    "value2",
    report={"sections": [{"title": "详情", "content": "..."}]},
    extra="附加数据",
)
```

- `success(*values)`：按 `returns` 顺序返回值；
- `failure(error, **detail)`：失败并记录原因；
- `report`：写入执行报告；
- `detail`：结构化附加信息。

## 7. 产出型函数与 `save_to`

### 7.1 声明 `output_param`

```python
@engine_function(
    name="extract",
    returns={"value": "str"},
    output_param="target",
)
def extract(self, ref: str, target: str = "") -> FunctionResult:
    ...
```

`output_param` 表示这个函数可以被 LLM 用作“产出型工具”，把返回值写入变量。

### 7.2 单返回值

```text
save_to = "变量名"
```

### 7.3 多返回值

```text
save_to = {"stdout": "stdout_var", "stderr": "stderr_var"}
```

可以只保存部分返回值。

### 7.4 FunctionCall 与 `save_to`

`FunctionCall` 直接使用节点上的 `returns` 接收名：

```yaml
returns: {result: str}
```

不需要在函数内部操作 `save_to`。

## 8. 自定义类型

插件自己的对象类型必须显式声明，不要退化成 `generics`。

### 8.1 声明类型

```python
class DemoSession:
    """演示会话对象"""

    def __init__(self, session_id: str):
        self.session_id = session_id


class DemoPlugin(PluginBase):
    name = "demo"
    description = "演示自定义类型"

    @property
    def custom_types(self):
        return {"demo_session": DemoSession}

    @engine_function(
        name="open_session",
        description="创建一个演示会话",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        returns={"session": "demo_session"},
        output_param="save_to",
    )
    def open_session(self, name: str):
        return DemoSession(name)


plugin = DemoPlugin()
```

注册后：

- `demo_session` 进入 `TYPE_REGISTRY`；
- 记录 `owner=demo`、`custom=true`；
- 不可由文本构造；
- 出现在 `GET /api/types`；
- 出现在插件卡片 / manifest 的 `custom_types`；
- 可用于函数 `returns`、树 inputs/outputs、`NewParam.x:demo_session`。

### 8.2 使用自定义类型

```yaml
n2:
  type: FunctionCall
  function: browser.open
  args: ["https://example.com"]
  returns: {page: page_object}

n3:
  type: FunctionCall
  function: ssh.create_session
  args: [Param.host]
  returns: {session: ssh_session}
```

后续节点通过 `Param.page` / `Param.session` 传递对象。

### 8.3 注册规则

- token 必须是 ASCII 标识符；
- 不能覆盖核心类型；
- 不同插件不能声明同名类型；
- 同一插件重载可替换自己的类型；
- 插件注销时自动移除类型；
- 自定义类型不允许文本构造（`constructible=false`）。

## 9. 配置、存储与前端扩展

> 配置项对所有插件适用。REST API、数据库模型、前端页面需要插件以代码包形式分发，主要用于**预置插件**；数据库里的单文件自定义插件只能使用标准库，不能 import FastAPI/SQLAlchemy。

### 9.1 配置

```python
@property
def config_schema(self):
    return [
        {
            "key": "api_base",
            "label": "API 地址",
            "type": "string",
            "default": "https://example.com",
            "required": True,
            "description": "服务地址",
        }
    ]

def get_config(self):
    return self._config

def set_config(self, config):
    self._config = config
```

配置持久化在插件记录中，前端「插件管理」页可编辑。

### 9.2 存储目录

```python
@property
def storage_dir(self):
    return "my_plugin_data"
```

### 9.3 前端页面

```python
@property
def frontend_manifest(self):
    return {
        "pages": [
            {
                "route": "/my-plugin",
                "label": "我的插件",
                "component": "MyPluginPage",
                "icon": "puzzle",
            }
        ]
    }
```

### 9.4 REST API

```python
def register_routes(self, app):
    from .api import router
    app.include_router(router, prefix="/api/plugins/my_plugin")
```

路由前缀固定为 `/api/plugins/{插件名}/`。

### 9.5 数据库模型

```python
def register_models(self, base):
    from . import models  # noqa: F401
```

模型应在 `Base.metadata.create_all` 前进入 metadata。表名建议 `plugin_{插件名}_*`。

## 10. 源码约束

用户自定义插件：

- 仅使用 Python 标准库；
- 不 import 其他插件 / `common` / 第三方库；
- 不使用项目内部模块；
- 插件名与提交名一致；
- 必须导出 `plugin` 变量；
- 保存时会试加载并检查函数、返回类型、自定义类型冲突。

常见错误：

| 错误 | 原因 |
|---|---|
| 语法错误 | Python 语法不合法 |
| 仅标准库 | import 了第三方库 |
| `插件未定义 ... 'plugin'` | 忘记 `plugin = MyPlugin()` |
| `name 不一致` | 源码内 name 与提交名不同 |
| `自定义类型 token 非法` | token 不是 ASCII 标识符 |
| `自定义类型已被 ... 注册` | 与其他插件冲突 |

## 11. 调试与验证

保存插件后，可通过以下接口检查：

```http
GET /api/plugins
GET /api/plugins/{name}/manifest
GET /api/plugins/{name}/functions
GET /api/functions
GET /api/types
```

### 11.1 测试 FunctionCall

```yaml
tree: 测试我的插件
nodes:
  r:
    type: Root
    body: n2
  n2:
    type: FunctionCall
    function: my_plugin.double
    args: ["3"]
    returns: {result: float}
root: r
```

执行后查看报告，确认：

- 函数调用参数；
- 返回值；
- 类型是否与 `returns` 一致；
- 自定义类型是否出现在 `/api/types`。

### 11.2 测试类型冲突

如果两个插件都声明 `foo`，后注册的插件会失败。修改 token，例如 `my_plugin_foo`。

## 12. 完整示例：带自定义类型的插件

```python
class Session:
    """演示会话"""

    def __init__(self, name: str):
        self.name = name


class DemoPlugin(PluginBase):
    name = "demo"
    description = "演示会话与加法"

    @property
    def custom_types(self):
        return {"demo_session": Session}

    @engine_function(
        name="open",
        description="创建演示会话",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "会话名"}},
            "required": ["name"],
        },
        returns={"session": "demo_session"},
        output_param="save_to",
    )
    def open(self, name: str):
        return Session(name)

    @engine_function(
        name="add",
        description="两个数相加",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
        returns={"result": "float"},
    )
    def add(self, a: float, b: float) -> float:
        return a + b


plugin = DemoPlugin()
```

对应行为树：

```yaml
tree: 使用演示插件
inputs:
  name: str
outputs:
  result: float
nodes:
  r:
    type: Root
    body: n2
  n2:
    type: Sequence
    name: 主流程
    actions: [n3, n4]
  n3:
    type: FunctionCall
    function: demo.open
    args: [Param.name]
    returns: {session: demo_session}
  n4:
    type: FunctionCall
    function: demo.add
    args: ["2", "3"]
    returns: {result: float}
root: r
```

## 13. 检查清单

- [ ] 插件名为小写字母/数字/下划线/短横线；
- [ ] 源码导出 `plugin`；
- [ ] 只 import 标准库；
- [ ] 函数都有 `@engine_function` 或 `@llm_function`；
- [ ] `returns` 类型合法；
- [ ] list 用 `array`，dict 用 `object`，插件对象声明自定义类型；
- [ ] 需要写变量时正确使用 `output_param` / FunctionCall returns；
- [ ] 自定义类型 token 全局唯一；
- [ ] 保存后检查 `/api/types`、`/api/functions` 与执行报告。
