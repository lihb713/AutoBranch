# M7 插件集（Plugin Set）Spec

> 原 **M1 浏览器驱动**、**M4 语义图**、**M5 引擎函数** 全部并入本模块的浏览器插件。

## Purpose

预置插件集（浏览器 / 计算 / SSH / 文件）与用户自定义插件，作为引擎核心之外的「能力层」：插件只返回值（业务值 + 报告附加信息），不写变量（引擎落笔）。

## Requirements

### 浏览器插件

浏览器插件 SHALL 自包含浏览器驱动、语义图生成、元素引用映射与页面对象：

- 网页操作函数：`open` / `activate` / `get_url` / `click` / `type` / `select` / `check` / `uncheck` / `scroll` / `wait` / `download` / `upload` / `extract` / `semantic_graph` / `clear_requests` / `get_response` / `http_request`。
- 页面对象（`PageObject`）作为泛型 `object` 值在变量中存储与传递；当前活动页由插件维护。

**元素角色分类（ARIA 对齐）**：`<input type="submit|button|reset">` SHALL 分类为 `button`（其标签存于 `value`）；`checkbox/radio/number/range` 分别映射；其余输入为 `textbox`。语义图序列化时，input 型按钮 SHALL 渲染 `value="..."`（标签），使 LLM 能识别按钮文本。

**元素引用（ref）选择器**：SHALL 按优先级生成定位选择器——DOM `id`（`#id`）→ 可见文本（`tag:has-text("文本")`）→ input 的 value 属性（`input[value="..."]`）→ **真实 DOM 索引路径**（`body > ... > tag:nth-of-type(n)`，由爬取端从真实 DOM 祖先生成，**含被快照过滤的中间容器**）。索引路径不依赖快照树过滤，任何深度的无 id/无文本元素都能精确定位（避免旧标签路径在中间容器被过滤后生成 `body > input` 之类匹配不到真实 DOM 的选择器）。

**打开页面**：`open` SHALL 使用 `wait_until="domcontentloaded"`（HTML 解析完成即返回），不等待可能永不触发的 `load` 事件（重型/流式页面），动态内容由后续 `semantic_graph` 读取。

**懒装配**：浏览器插件 `init(runtime)` 时冷启动驱动（真实浏览器才启动）；纯计算行为树零浏览器开销。
- `semantic_graph`（"看页面"）时强制截图并写入报告（不再由编排器无条件截）。
- 打开失败 / 元素缺失 / 页面失效均返回错误结果（含原因），LLM 可修正。

### 计算插件

确定性纯函数：`multiply(a, b)`、`add(a, b)`、`sum(values)`、`sort(data, desc)`、`compare(a, b)`；同输入同输出、无副作用。

### SSH 插件

会话对象（`SSHConnection`）作为泛型 `object` 值；`create_session`（端口/认证/超时）、`ssh_exec`（命令超时、非零退出码 = 失败）、`close_session`；release 关闭全部会话。

### 文件插件

`read` / `write` / `diff`；路径以引擎工作目录为基址；失败返回原因；单文件上限 10MB。

### 用户自定义插件（开发指南）

自定义插件为单文件 Python 脚本（源码存 DB `source` 字段），在「插件管理」页编写，保存即校验并重载生效。

**模板**：

```python
class MyPlugin(PluginBase):
    name = "my_plugin"            # 插件名（须与提交名一致）
    description = "我的自定义插件" # 能力说明

    @engine_function(
        name="hello",              # 插件内函数名（全名 my_plugin.hello；跨插件可同名）
        description="返回问候语",   # 函数说明（供 LLM 工具）
        parameters={...},          # JSON Schema 参数定义
        returns=("message",),      # 多返回值名（按序）
        output_param=None,         # 产出型工具：变量目标参数名（None=非产出型）
    )
    def hello(self, who="world"):
        return f"hello {who}"

plugin = MyPlugin()    # 必须以 plugin 变量导出实例
```

**约束与要点**：
- 仅用 Python 标准库；直接使用 exec 注入的 `PluginBase` / `engine_function` / `FunctionResult`（**不 import**）。
- 不 import 其他插件 / `common` / 三方库；插件名小写字母/数字/`_`/`-`、不与预置同名。
- `@engine_function` 显式注册对外函数；未标注不注册。
- 函数只返回值（裸值或 `FunctionResult`）、不写变量（引擎落笔）。
- `output_param`：产出型工具声明变量目标参数名，引擎按节点 `NewParam.名[:类型]` 声明类型 coerce 后写入变量。
- 删除插件会置空引用它的行为树 FunctionCall 引用。

**使用方式**：
- FunctionCall 节点：`function: <插件名.函数名>`（全名，如 `compute.add`）+ `args`（变量/字面量）+ `returns`（回收多返回值）。
- Action/Condition 叶子：LLM 经 `use_capability` 加载能力后调用其函数（工具名为转义全名 `插件__函数`，如 `compute__multiply`）。

## 关键实现

- **预置插件位于 `autobranch/plugins/`**（工具的一部分，随工具分发）：
  - `autobranch/plugins/browser/`：浏览器插件——**自包含**浏览器驱动（`driver/` 子包）、语义图生成（`semantic_graph/` 子包）、元素引用映射（`refmap.py`）、页面探针（`probe.py`）+ 插件类（`__init__.py`）。
  - `autobranch/plugins/compute/`、`autobranch/plugins/ssh/`、`autobranch/plugins/file/`、`autobranch/plugins/common/`（共享库）。
- 每个插件包以 `plugin` 变量暴露 `PluginBase` 实例；引擎启动经 `load_builtin_plugins` 扫描 `autobranch/plugins` 注册。
- 兼容转发层：`autobranch.browser` / `autobranch.semantic_graph` / `autobranch.engine.probe` / `autobranch.engine.refmap` 为薄转发（物理实现在浏览器插件内），供引擎核心 / 旧非插件路径引用。