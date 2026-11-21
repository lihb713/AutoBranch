# AutoBranch 内置插件介绍

> 本文列出 AutoBranch 当前内置插件、函数、参数、返回值和自定义类型。
>
> 相关文档：
> - [行为树指南](behavior-tree-guide.md)
> - [插件开发指南](plugin-development-guide.md)
> - [完整用户手册](user-guide.md)

## 1. 插件总览

| 插件 | 能力 | 自定义类型 |
|---|---|---|
| `browser` | 浏览器打开/操作/语义图/请求/上传下载 | `page_object` |
| `compute` | 数值计算、排序、比较 | — |
| `transform` | 列表/字典/字符串/JSON/正则/比较 | — |
| `ssh` | SSH 会话、命令、交互通道、文件传输 | `ssh_session` |
| `file` | 文件读写、对比、文件管理平台 | — |
| `http` | 独立 HTTP 请求 | — |
| `vars` | 直接把值写入变量 | — |

插件声明的自定义类型会出现在：

```http
GET /api/types
GET /api/plugins
GET /api/plugins/{name}/manifest
```

### 1.1 可见性说明

- **用户可见**：可以用 `FunctionCall` 节点调用，也会出现在 `/api/functions`；
- **仅 LLM**：不能写进 FunctionCall，只能在 Action/Condition 中由 LLM 选择调用（如语义图、页面点击）。

浏览器插件只把少量函数开放给 FunctionCall，大量网页操作是 LLM 专用接口。

### 1.2 如何查看实时函数清单

```http
GET /api/functions
GET /api/plugins/browser/functions
```

或在「插件管理」页点击「查看函数详情」。

## 2. 浏览器插件 `browser`

浏览器插件提供：

- 页面打开与切换；
- 语义图与元素引用 `ref`；
- 点击/输入/选择/滚动/等待；
- 请求记录与响应读取；
- 文件上传/下载；
- 与文件管理平台互通。

### 2.1 自定义类型

| token | Python 类 | 说明 |
|---|---|---|
| `page_object` | `PageObject` | 页面对象，`open` 返回；不可文本构造 |

页面对象通常通过 `save_to` 或 FunctionCall `returns` 保存：

```yaml
n2:
  type: FunctionCall
  function: browser.open
  args: ["https://example.com"]
  returns: {page: page_object}
```

之后在 LLM 叶子中用 `Param.page` 引用。

### 2.2 用户可见函数（可 FunctionCall）

| 函数 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `browser.open` | `url: str` | `page: page_object` | 打开 URL，新页签设为活动页 |
| `browser.get_url` | — | `url: str` | 取当前活动页 URL |
| `browser.scroll` | `direction: str` | — | 滚动：`up/down/left/right/top/bottom` |
| `browser.wait` | `condition: str` | — | 等待 `selector:` / `text:` / `url:` 条件 |

示例：

```yaml
n2:
  type: Sequence
  name: 打开并确认
  actions: [n3, n4]
n3:
  type: FunctionCall
  function: browser.open
  args: ["https://example.com"]
  returns: {page: page_object}
n4:
  type: FunctionCall
  function: browser.wait
  args: ["text: 欢迎"]
```

### 2.3 仅 LLM 的页面/标签页函数

| 函数 | 参数 | 返回 |
|---|---|---|
| `browser.semantic_graph` | `scope: str`, `lod: int` | `graph: object` |
| `browser.activate` | `page` | `page: page_object` |
| `browser.list_tabs` | — | — |
| `browser.switch_tab` | `tab_id: str` | — |

- `semantic_graph` 每次生成最新语义图；生成后旧 `ref` 失效；
- `activate` 用于切换已保存页面对象；
- `list_tabs` / `switch_tab` 用于多标签页。

### 2.4 仅 LLM 的元素操作

| 函数 | 参数 |
|---|---|
| `browser.click` | `ref` |
| `browser.type` | `ref`, `text` |
| `browser.press` | `ref`, `key` |
| `browser.select` | `ref`, `option` |
| `browser.check` / `browser.uncheck` | `ref` |
| `browser.extract` | `ref`（产出型 `target`） |
| `browser.download` | `ref` |
| `browser.upload` | `ref`, `path` |

这些函数依赖当前页面的语义图 `ref`，由 LLM 在叶子内部决定何时调用。

### 2.5 仅 LLM 的捕获操作

捕获函数会执行操作，并把触发的 API 响应批量保存到变量：

| 函数 | 参数 | 返回 |
|---|---|---|
| `browser.click_capture` | `ref` | `responses: str` |
| `browser.type_capture` | `ref`, `text` | `responses: str` |
| `browser.press_capture` | `ref`, `key` | `responses: str` |
| `browser.select_capture` | `ref`, `option` | `responses: str` |
| `browser.check_capture` | `ref` | `responses: str` |
| `browser.uncheck_capture` | `ref` | `responses: str` |
| `browser.scroll_capture` | `direction` | `responses: str` |
| `browser.upload_capture` | `ref`, `path` | `responses: str` |

### 2.6 仅 LLM 的请求读取

| 函数 | 参数 | 返回 |
|---|---|---|
| `browser.clear_requests` | — | — |
| `browser.list_requests` | — | — |
| `browser.get_request_headers` | — | — |
| `browser.get_response` | `method`, `url_pattern` | — |
| `browser.get_responses` | — | `responses: str` |
| `browser.page_request` | `method`, `url`, `headers?`, `body?` | `body: str` |

注意：

- `http.request` 是独立请求，不携带页面 cookie；
- `browser.page_request` 在当前页面上下文发起请求，会自动携带 cookie；
- 复杂认证可先 `get_request_headers` 分析，再补 headers。

### 2.7 仅 LLM 的文件互通

| 函数 | 参数 | 说明 |
|---|---|---|
| `browser.download` | `ref` | 下载到本地 |
| `browser.upload` | `ref`, `path` | 上传本地文件 |
| `browser.download_to_platform` | `ref`, `file_path?` | 下载到文件管理平台 |
| `browser.upload_from_platform` | `ref`, `file_path` | 从文件管理平台上传 |

## 3. 计算插件 `compute`

全部为用户可见函数，可直接 FunctionCall。

| 函数 | 参数 | 返回 |
|---|---|---|
| `compute.add` | `a`, `b` | `result: float` |
| `compute.subtract` | `a`, `b` | `result: float` |
| `compute.multiply` | `a`, `b` | `result: float` |
| `compute.divide` | `a`, `b` | `result: float` |
| `compute.floor_divide` | `a`, `b` | `result: int` |
| `compute.modulo` | `a`, `b` | `result: float` |
| `compute.power` | `a`, `b` | `result: float` |
| `compute.sqrt` | `value` | `result: float` |
| `compute.abs_value` | `value` | `result: float` |
| `compute.negate` | `value` | `result: float` |
| `compute.round_value` | `value`, `digits?` | `result: float` |
| `compute.increment` | `value`, `step?` | `result: float` |
| `compute.decrement` | `value`, `step?` | `result: float` |
| `compute.sum` | `values: array` | `total: float` |
| `compute.average` | `values: array` | `result: float` |
| `compute.min_values` | `values: array` | `result: float` |
| `compute.max_values` | `values: array` | `result: float` |
| `compute.clamp` | `value`, `low`, `high` | `result: float` |
| `compute.percentage` | `part`, `total` | `result: float` |
| `compute.sort` | `data: array`, `desc?` | `result: array` |
| `compute.compare` | `a`, `b`, `op?` | `result: bool` |

示例：

```yaml
n2:
  type: FunctionCall
  function: compute.add
  args: [Param.a, Param.b]
  returns: {total: float}
```

除数为 0、负数开方、空列表聚合等会返回失败。

## 4. 数据变换插件 `transform`

全部为用户可见函数。`generics` 表示任意值（不转换）。

| 函数 | 参数 | 返回 |
|---|---|---|
| `transform.get_path` | `data`, `path`, `required?`, `default?` | `value: generics` |
| `transform.get_index` | `data: array`, `index`, `required?`, `default?` | `value: generics` |
| `transform.get_key` | `data: object`, `key`, `required?`, `default?` | `value: generics` |
| `transform.split` | `text`, `separator`, `maxsplit?` | `values: array` |
| `transform.join` | `values: array`, `separator` | `text: str` |
| `transform.concat` | `a`, `b`, `c?`, `d?`, `e?`, `separator?` | `text: str` |
| `transform.format` | `template`, `values: object` | `text: str` |
| `transform.contains` | `text`, `needle`, `ignore_case?` | `result: bool` |
| `transform.index_of` | `text`, `needle`, `ignore_case?` | `index: int` |
| `transform.replace` | `text`, `old`, `new`, `count?` | `text: str` |
| `transform.strip` | `text`, `chars?` | `text: str` |
| `transform.slice` | `value`, `start?`, `end?`, `step?` | `value: generics` |
| `transform.length` | `value` | `length: int` |
| `transform.keys` | `data: object` | `keys: array` |
| `transform.values` | `data: object` | `values: array` |
| `transform.compare` | `a`, `b`, `op?`, `ignore_case?` | `result: bool` |
| `transform.to_string` | `value` | `text: str` |
| `transform.to_int` | `value` | `value: int` |
| `transform.to_number` | `value` | `value: float` |
| `transform.to_bool` | `value` | `value: bool` |
| `transform.json_parse` | `text` | `value: generics` |
| `transform.json_dumps` | `value`, `indent?` | `text: str` |
| `transform.regex_match` | `text`, `pattern`, `full?`, `ignore_case?` | `result: bool` |
| `transform.regex_extract` | `text`, `pattern`, `group?`, `ignore_case?` | `text: str` |
| `transform.regex_findall` | `text`, `pattern`, `ignore_case?` | `values: array` |
| `transform.append` | `list_var`, `value` | `list: str`（产出型） |
| `transform.dict_set` | `dict_var`, `key`, `value` | `dict: str`（产出型） |

示例：拼接 URL

```yaml
n2:
  type: FunctionCall
  function: transform.format
  args: ["http://{host}:{port}/api", Param.payload]
  returns: {url: str}
```

其中 `payload` 可声明为 `object`，入参写：

```json
{"host":"example.test","port":8080}
```

`append` / `dict_set` 返回 JSON **字符串**，适合 ForEach 跨轮累积；如果只是普通 list/dict，优先直接使用 `array` / `object` 变量。

## 5. SSH 插件 `ssh`

### 5.1 自定义类型

| token | Python 类 | 说明 |
|---|---|---|
| `ssh_session` | `SSHConnection` | SSH 会话对象；不可文本构造 |

`create_session` 返回 `session: ssh_session`，后续用 `Param.session` 传递。

### 5.2 函数

| 函数 | 参数 | 返回 |
|---|---|---|
| `ssh.create_session` | `host`, `port?`, `user?`, `pwd?`, `key?`, `timeout?`, `proxy?`, `jump?` | `session: ssh_session`（产出型） |
| `ssh.close_session` | `session` | — |
| `ssh.ssh_exec` | `session`, `command`, `timeout?`, `stdin?`, `interactive?`, `idle_timeout?` | `stdout/stderr/exit_code/channel_id/exited` |
| `ssh.ssh_send` | `session`, `channel_id`, `data`, `newline?` | — |
| `ssh.ssh_read` | `session`, `channel_id`, `idle_timeout?` | `stdout/stderr/exit_code/exited` |
| `ssh.ssh_close_channel` | `session`, `channel_id` | — |
| `ssh.upload_file` | `session`, `file_path`, `remote_path`, `timeout?` | `size/path` |
| `ssh.download_file` | `session`, `remote_path`, `file_path?`, `timeout?` | `size/path` |
| `ssh.upload_dir` | `session`, `dir_path`, `remote_dir`, `timeout?` | `files/path` |
| `ssh.download_dir` | `session`, `remote_dir`, `dir_path?`, `timeout?` | `files/path` |

### 5.3 示例

```yaml
n2:
  type: FunctionCall
  function: ssh.create_session
  args: ["10.0.0.10"]
  kwargs:
    user: root
    pwd: secret
  returns: {session: ssh_session}

n3:
  type: FunctionCall
  function: ssh.ssh_exec
  args: [Param.session, "ls -la /tmp"]
  returns: {stdout: str, exit_code: int}
```

说明：

- `proxy` 为 SOCKS5：`{host, port, user?, pwd?}`；
- `jump` 为跳板机：`{host, port?, user?, pwd?, key?, timeout?, proxy?}`；
- 有 `jump` 时 `proxy` 用于连接跳板机；
- 非交互命令等待 exit-status，非零退出码算失败；
- `interactive=true` 使用 PTY，返回 `channel_id` 供后续 send/read。

## 6. 文件插件 `file`

文件插件有两类能力：

- 工作区文件：`read` / `write` / `diff` / `md5`；
- 文件管理平台：目录与文件记录、下载/上传、目录 CRUD。

所有路径都是**相对文件管理根目录**的相对路径，禁止绝对路径和 `..` 越界。

| 函数 | 参数 | 返回 |
|---|---|---|
| `file.read` | `path` | `content: str` |
| `file.write` | `path`, `content` | — |
| `file.diff` | `file_a`, `file_b` | `diff: object` |
| `file.md5` | `path` | `md5: str` |
| `file.list_dir` | `path` | `entries: array` |
| `file.mkdir` | `path` | `directory: object` |
| `file.rmdir` | `path`, `recursive?` | — |
| `file.mvdir` | `path`, `new_path` | `directory: object` |

示例：

```yaml
n2:
  type: FunctionCall
  function: file.write
  args: ["reports/result.txt", Param.content]

n3:
  type: FunctionCall
  function: file.md5
  args: ["reports/result.txt"]
  returns: {md5: str}
```

文件管理平台 API：

```http
GET  /api/plugins/file/entries?path=reports
GET  /api/plugins/file/files
POST /api/plugins/file/files
GET  /api/plugins/file/download?path=reports/result.txt
```

## 7. HTTP 插件 `http`

独立发起 HTTP 请求，不依赖浏览器页面。

| 函数 | 参数 | 返回 |
|---|---|---|
| `http.request` | `method`, `url`, `headers?`, `params?`, `body?`, `json?`, `timeout?` | `status: int`, `body: str`, `headers: object` |

示例：

```yaml
n2:
  type: FunctionCall
  function: http.request
  args: ["GET", "https://api.example.com/health"]
  returns: {status: int, body: str}
```

- `headers` / `params` / `json` 是 `object`，可直接传 dict 或 JSON 文本；
- 认证头需要显式提供；
- 需要页面 cookie 时使用浏览器插件的 `page_request`。

## 8. 变量插件 `vars`

| 函数 | 参数 | 返回 |
|---|---|---|
| `vars.set` | `value1`, `value2?`, `value3?` | `value1/value2/value3: str`（产出型） |

用于把 LLM 推理结果写入变量：

```yaml
n2:
  type: FunctionCall
  function: vars.set
  args: ["hello"]
  returns: {value1: str}
```

## 9. 常见问题

### 9.1 为什么浏览器函数不能写进 FunctionCall？

浏览器大量函数是 **LLM-only**（`@llm_function`），因为它们依赖当前页面语义图 `ref` 与上下文。FunctionCall 只支持用户可见函数。

需要 FunctionCall 时可用：

- `browser.open`
- `browser.get_url`
- `browser.scroll`
- `browser.wait`

其他操作请在 Action 描述中让 LLM 执行。

### 9.2 `page_object` / `ssh_session` 能作为树入参吗？

不能直接由文本构造。它们只能：

- 由插件返回；
- 通过 `ref` 传递；
- 在树内用 `Param` 使用。

`GET /api/types` 会显示 `constructible=false`。

### 9.3 `object` 和 `generics` 有什么区别？

- `object`：确定是 Python `dict`；
- `array`：确定是 Python `list`；
- `generics`：不确定类型，任意值；
- 插件自己的对象应声明为自定义类型，而不是 `generics`。

### 9.4 怎样确认函数参数与返回值？

直接调用：

```http
GET /api/functions
GET /api/plugins/{name}/functions
```

前端「插件管理 → 查看函数详情」也会列出参数、返回类型与可见性。
