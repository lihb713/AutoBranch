# M7 插件集（Plugin Set）Spec

> 原 **M1 浏览器驱动**、**M4 语义图**、**M5 引擎函数** 全部并入本模块的浏览器插件。

## Purpose

预置插件集（浏览器 / 计算 / SSH / 文件 / HTTP / 变量 / 数据变换）与用户自定义插件，作为引擎核心之外的「能力层」：插件只返回值（业务值 + 报告附加信息），不写变量（引擎落笔）。

## Requirements

### 浏览器插件

浏览器插件 SHALL 自包含浏览器驱动、语义图生成、元素引用映射与页面对象：

- 网页操作函数（LLM 全量）：`open` / `activate` / `get_url` / `click` / `type` / `press` / `select` / `check` / `uncheck` / `scroll` / `wait` / `download` / `upload` / `extract` / `semantic_graph` / `clear_requests` / `list_requests` / `get_response` / `get_responses` / `get_request_headers` / `page_request` / `list_tabs` / `switch_tab` / `click_capture` / `type_capture` / `press_capture` / `select_capture` / `check_capture` / `uncheck_capture` / `scroll_capture` / `upload_capture`。
- **用户可见子集**（FunctionCall / 函数清单）：`open` / `get_url` / `scroll` / `wait`；其余（含 `semantic_graph`、`page_request`、`get_response`、`click` 等依赖 ref/页面上下文的接口）用 `@llm_function` 注册为仅 LLM 可见。独立 HTTP 请求由 `http` 插件提供 `http.request`（用户可见）。
- **HTTP 能力拆分**：独立请求用 `http.request(method, url, headers?, params?, body?, json?, timeout?)`（用户可见，返回 status/body/headers）；页面内请求用 `page_request`（cookie 自动携带，LLM-only）；`list_requests` / `get_response` / `get_responses` / `clear_requests` 用于页面请求记录。
- **多标签页**：`list_tabs` / `switch_tab` 管理新标签页；操作返回 `new_tabs`/`tabs_hint`。
- **捕获操作**：`click_capture` / `type_capture` / `press_capture` / `select_capture` / `check_capture` / `uncheck_capture` / `scroll_capture` / `upload_capture` 封装 clear→操作→批量响应。
- 页面对象（`PageObject`）作为 `generics` 值在变量中存储与传递；当前活动页由插件维护。
- **文件平台联动**：`upload_from_platform(ref, file_path)` / `download_to_platform(ref, file_path?)` 从文件管理平台取文件上传到页面，或把页面下载保存到文件管理平台（平台路径）。

**元素角色分类（ARIA 对齐）**：`<input type="submit|button|reset">` SHALL 分类为 `button`（其标签存于 `value`）；`checkbox/radio/number/range` 分别映射；其余输入为 `textbox`。语义图序列化时，input 型按钮 SHALL 渲染 `value="..."`（标签），使 LLM 能识别按钮文本。

**元素引用（ref）选择器**：SHALL 按优先级生成定位选择器——DOM `id`（`#id`）→ 可见文本（`tag:has-text("文本")`）→ input 的 value 属性（`input[value="..."]`）→ **真实 DOM 索引路径**（`body > ... > tag:nth-of-type(n)`，由爬取端从真实 DOM 祖先生成，**含被快照过滤的中间容器**）。索引路径不依赖快照树过滤，任何深度的无 id/无文本元素都能精确定位（避免旧标签路径在中间容器被过滤后生成 `body > input` 之类匹配不到真实 DOM 的选择器）。

**打开页面**：`open` SHALL 使用 `wait_until="domcontentloaded"`（HTML 解析完成即返回），不等待可能永不触发的 `load` 事件（重型/流式页面），动态内容由后续 `semantic_graph` 读取。

**懒装配**：浏览器插件 `init(runtime)` 时冷启动驱动（真实浏览器才启动）；纯计算行为树零浏览器开销。
- `semantic_graph`（"看页面"）时强制截图并写入报告（不再由编排器无条件截）。
- 打开失败 / 元素缺失 / 页面失效均返回错误结果（含原因），LLM 可修正。

### 计算插件

确定性纯函数：`add` / `subtract` / `multiply` / `divide` / `floor_divide` / `modulo` / `power` / `sqrt` / `abs_value` / `negate` / `round_value` / `sum` / `average` / `min_values` / `max_values` / `clamp` / `percentage` / `increment` / `decrement` / `sort` / `compare`；同输入同输出、无副作用。

- `divide` / `floor_divide` / `modulo` / `percentage` 除数为 0 返回失败；`sqrt` 负数返回失败。
- `compare(a, b, op)` 支持 `gt/ge/lt/le/eq/ne`，默认 `gt`。

### 数据变换插件

`transform` 提供无副作用的数据提取/变换：

- 路径/索引/键：`get_path(data, path)`（如 `0.a.b.1` / `a[0].b[-1]`）、`get_index`、`get_key`；可选 `required=false` + `default`。
- 字符串：`split` / `join` / `contains` / `index_of` / `replace` / `strip` / `concat`（a~e 顺序拼接）/ `format`（`{name}` 模板 + values 字典）。
- 容器：`length` / `slice` / `keys` / `values`。
- 转换：`to_string` / `to_int` / `to_number` / `to_bool` / `json_parse` / `json_dumps`。
- 比较：`compare(a, b, op, ignore_case)`，支持 `eq/ne/gt/ge/lt/le/contains/startswith/endswith`。
- 正则：`regex_match` / `regex_extract` / `regex_findall`。
- 累积：`append` / `dict_set`（产出型 JSON 字符串，ForEach 跨轮收集结果）。

### vars 插件

`vars.set(value1, value2?, value3?)`：原样返回传入值，配合 `output_param="save_to"` 把 LLM 推理产出的文本/数据写入变量（多返回值映射可部分保存）。

### http 插件

独立 HTTP 请求：`http.request(method, url, headers?, params?, body?, json?, timeout?)`，返回 `status/body/headers`，认证由调用方在 headers 显式提供。

### SSH 插件

会话对象（`SSHConnection`）作为 `generics` 值。

- `create_session(host, port?, user?, pwd?/key?, timeout?, proxy?, jump?)`：直连；`proxy` 为 SOCKS5；`jump` 为 SSH 跳板机。有 jump 时 proxy 用于连接跳板机；jump→目标改为在跳板机 PTY shell 中执行 `ssh` 命令（兼容禁用 `direct-tcpip` 的环境），目标认证需提供 `pwd`。
- `ssh_exec(session, command, timeout?, stdin?, interactive?, idle_timeout?)`：
  - 默认非交互：流式读取 stdout/stderr，直到 SSH 通道返回 exit-status；返回 `stdout/stderr/exit_code/channel_id/exited`，非零退出码失败。
  - `interactive=true`：PTY 模式，idle_timeout 无输出后返回当前输出与 `channel_id`；不强制等待退出。
  - 跳板机模式：非交互命令通过唯一标记（start/exit）分割目标 PTY shell 输出并解析退出码；交互命令使用 `channel_id="jump-shell"`。
- 交互：`ssh_send(session, channel_id, data, newline?)`、`ssh_read(session, channel_id, idle_timeout?)`、`ssh_close_channel`。
- 文件平台联动：`upload_file` / `download_file` 单文件互通；`upload_dir` / `download_dir` 递归目录互通；直连用 SFTP，jump shell 用 base64（目录下载用 `find` 枚举）。
- SSH stdout/stderr/交互输出 SHALL 过滤 ANSI 转义序列（颜色/控制码）；jump shell 非交互命令输出 SHALL 剔除末尾命令提示符行。
- `close_session` / `release` 关闭目标、跳板与全部通道。
- 依赖 `paramiko` + `PySocks`（pyproject 依赖）。

### 文件插件

- 工作区函数：`read` / `write` / `diff` / `md5`；所有路径均限制在文件管理根目录 `autobranch/plugins/file/data/` 下（相对路径，禁止绝对路径与 `..` 越界）。
- 文件管理平台：目录表 `plugin_file_directories` + 文件表 `plugin_file_records`，所有文件/目录使用 POSIX 相对路径（如 `reports/2026/a.txt`）。
- 目录能力：`list_dir` / `mkdir` / `rmdir` / `mvdir`；目录重命名同步更新后代文件路径。
- API：`/api/plugins/file/entries`、`/directories` CRUD、`/files`（支持 `path` form）、`/download?path=`（目录返回 ZIP）。
- 前端文件管理支持目录导航、新建/重命名/递归删除、上传文件、上传目录（多文件保留相对路径）、下载文件/目录；文件列表展示 MD5。
- 单文件上限 10MB（可配置）。

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
        returns={"message": "str"}, # 返回参数名 → 类型（按序）
        output_param=None,         # 产出型工具：变量目标参数名（None=非产出型）
    )
    def hello(self, who="world"):
        return f"hello {who}"

plugin = MyPlugin()    # 必须以 plugin 变量导出实例
```

**约束与要点**：
- 仅用 Python 标准库；直接使用 exec 注入的 `PluginBase` / `engine_function` / `FunctionResult`（**不 import**）。
- 不 import 其他插件 / `common` / 三方库；插件名小写字母/数字/`_`/`-`、不与预置同名。
- `@engine_function` 显式注册**用户与 LLM 均可见**的函数；`@llm_function` 注册**仅 LLM 可见**的函数（技术性接口）；未标注不注册。
- `returns` 必须为 `{返回参数名: 类型}` 映射；名称 ASCII、类型合法（`str/int/float/bool/array/object/generics/page_ref`）；列表用 `array`、字典用 `object`、无法归类对象用 `generics`、页签引用用 `page_ref`；未填写接收名时后端生成 `<节点id>_<返回参数名>`。
- 函数只返回值（裸值或 `FunctionResult`）、不写变量（引擎落笔）。
- `output_param`：产出型工具声明变量目标参数名，引擎按节点 `NewParam.名[:类型]` 声明类型 coerce 后写入变量。
- 删除插件会置空引用它的行为树 FunctionCall 引用。

**使用方式**：
- FunctionCall 节点：`function: <插件名.函数名>`（全名，如 `compute.add`）+ `args`（位置变量/字面量）+ `kwargs`（命名可选参数，支持嵌套对象/列表）+ `returns`（回收多返回值）。
- Action/Condition 叶子：LLM 经 `use_capability` 加载能力后调用其函数（工具名为转义全名 `插件__函数`，如 `compute__multiply`）。

## 关键实现

- **预置插件位于 `autobranch/plugins/`**（工具的一部分，随工具分发）：
  - `autobranch/plugins/browser/`：浏览器插件——**自包含**浏览器驱动（`driver/` 子包）、语义图生成（`semantic_graph/` 子包）、元素引用映射（`refmap.py`）、页面探针（`probe.py`）、**代理路由**（`proxy.py` + `proxy.config.json` 配置 + `proxy.config.example.json` 示例）+ 插件类（`__init__.py`）。
  - `autobranch/plugins/compute/`、`autobranch/plugins/ssh/`、`autobranch/plugins/file/`、`autobranch/plugins/transform/`、`autobranch/plugins/common/`（共享库）。
- 每个插件包以 `plugin` 变量暴露 `PluginBase` 实例；引擎启动经 `load_builtin_plugins` 扫描 `autobranch/plugins` 注册。
- **浏览器代理路由**（browser-proxy-routing）：代理决策不进行为树描述，由插件内 `proxy.config.json`（缺失则不启用）按站点规则匹配——`default` + `profiles`（system / direct / 自定义）+ `rules`（首条命中）。`BrowserDriver.open(url)` 按 URL 路由到对应会话（context-per-mode，懒建）；`direct` 经独立 `--no-proxy-server` 浏览器承载（Playwright 不支持 context 级 `direct://`）；system/custom 共用一个默认浏览器。
- 兼容转发层：`autobranch.browser` / `autobranch.semantic_graph` / `autobranch.engine.probe` / `autobranch.engine.refmap` 为薄转发（物理实现在浏览器插件内），供引擎核心 / 旧非插件路径引用。