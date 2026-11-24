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
| `predicate` | 条件表达式常用单 bool 谓词 | — |
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

### 1.2 如何选择插件

| 需求 | 推荐 | 原因 |
|---|---|---|
| 操作真实网页、点击/输入/上传下载 | `browser` | 需要页面上下文、语义图和页面 cookie |
| 调已知 HTTP API，不需要页面 | `http` | 更轻量，不启动浏览器 |
| 数值运算/排序/聚合 | `compute` | 纯函数，确定性 |
| 字符串/JSON/列表/字典变换 | `transform` | 不依赖外部服务 |
| 把 LLM 自己生成的值写入变量 | `vars` | 没有具体插件函数时的通用载体 |
| 远程命令/文件传输 | `ssh` | 会话复用、退出码、跳板机 |
| 平台文件存取、目录管理 | `file` | 统一路径、MD5、目录 API |

### 1.3 如何查看实时函数清单

```http
GET /api/functions
GET /api/plugins/browser/functions
```

或在「插件管理」页点击「查看函数详情」。

## 2. 浏览器插件 `browser`

### 2.0 为什么需要浏览器插件

浏览器插件不是“把 Playwright 包一层”这么简单，它解决了三个问题：

1. **LLM 如何理解页面**：通过语义图把 DOM 转成可读结构；
2. **LLM 如何稳定引用元素**：通过 `ref` 和真实 DOM 路径，避免每次重新猜 CSS；
3. **如何记录上下文**：页面对象、请求记录、截图、下载文件都随执行报告保存。

因此浏览器插件既提供用户可见的少数确定性函数（open/wait/scroll/get_url），也提供大量 LLM-only 的上下文操作（click/type/semantic_graph）。

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
| `browser.activate` | `page: page_object` | `page: page_object` |
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

### 2.6 请求读取与页面请求

| 函数 | 参数 | 返回 | 可见性 |
|---|---|---|---|
| `browser.clear_requests` | — | — | LLM-only |
| `browser.list_requests` | — | — | LLM-only |
| `browser.get_request_headers` | — | `headers: str` | 用户可见 |
| `browser.get_header_value` | `name` | `value: str`, `header_name: str` | 用户可见 |
| `browser.get_response` | `method`, `url_pattern` | — | LLM-only |
| `browser.get_responses` | — | `responses: str` | LLM-only |
| `browser.page_request` | `method`, `url`, `headers?`, `body?`, `json_body?` | `body: str` | 用户可见 |

注意：

- `http.request` 是独立请求，不携带页面 cookie；
- `browser.page_request` 在当前页面上下文发起请求，会自动携带 cookie；可用 FunctionCall 确定性调用；
- `page_request.json_body` 接受 dict/list，自动 JSON 序列化并补 `Content-Type: application/json`；与 `body` 互斥；
- `get_header_value(name)` 大小写不敏感地从最新请求头中取单字段，找不到返回 NOT_FOUND；
- 复杂认证可先 `get_request_headers` / `get_header_value` 分析，再补 headers。

### 2.7 仅 LLM 的文件互通

| 函数 | 参数 | 说明 |
|---|---|---|
| `browser.download` | `ref` | 下载到本地 |
| `browser.upload` | `ref`, `path` | 上传本地文件 |
| `browser.download_to_platform` | `ref`, `file_path?` | 下载到文件管理平台 |
| `browser.upload_from_platform` | `ref`, `file_path` | 从文件管理平台上传 |

## 3. 计算插件 `compute`

### 3.0 为什么需要计算插件

计算是典型的“完全确定、完全不需要 LLM”的能力：

- 两数相加、百分比、聚合；
- 排序、比较；
- 这些操作交给 LLM 既慢又可能算错。

因此 `compute` 全部是纯函数，既可被 FunctionCall 直接调用，也可被 LLM 作为工具调用。

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

### 4.0 为什么需要数据变换插件

行为树里的数据经常不是“刚算出来的数”，而是：

- 一段 JSON 里的某个字段；
- 一个 URL 模板；
- 正则提取结果；
- 列表拼接；
- 字典键值。

如果这些都用 LLM 做，会产生随机性和额外成本。`transform` 提供确定性的“数据搬运/清洗”能力。

### 4.1 为什么 `append` / `dict_set` 返回 JSON 字符串

ForEach 跨轮累积时，需要一个能不断传递的容器。早期实现用 JSON 字符串承载：

- 空字符串表示空列表/空字典；
- 每次 append/dict_set 返回完整 JSON 字符串；
- 下一轮继续传入。

如果你只是普通 list/dict 传递，优先使用 `array` / `object` 变量，不必使用 append/dict_set。

全部为用户可见函数。`generics` 表示任意值（不转换）。

| 函数 | 参数 | 返回 |
|---|---|---|
| `transform.get_path` | `data`, `path`, `required?`, `default?` | `value: generics` |
| `transform.get_index` | `data: array`, `index`, `required?`, `default?` | `value: generics` |
| `transform.get_key` | `data: object`, `key`, `required?`, `default?` | `value: generics` |
| `transform.project` | `items: array`, `fields: array` | `items: array` |
| `transform.filter_eq` | `items: array`, `field`, `value` | `items: array` |
| `transform.find_one` | `items: array`, `field`, `value`, `target_field`, `default?` | `value: generics` |
| `transform.join_field` | `items`, `ref_field`, `lookup_list`, `field`, `target_field`, `alias`, `default?`, `loose_match?` | `items: array` |
| `transform.rename_fields` | `items: array`, `rename_map: object` | `items: array` |
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

`join_field` 默认严格相等；跨系统 ID 常见 str/int 混用时设置 `loose_match: true`，按 `str(a) == str(b)` 匹配。

## 5. SSH 插件 `ssh`

### 5.0 为什么需要 SSH 插件

SSH 不是一次性的命令字符串，而是有生命周期的会话：

- 建连成本高，应复用；
- 需要密码/私钥/SOCKS5/跳板机；
- 非交互命令要拿退出码；
- 交互命令要持续 send/read；
- 文件传输需要 SFTP/跳板机兼容方案。

因此 SSH 插件把连接抽象成 `ssh_session` 自定义类型，而不是每次调用都重新传主机密码。

### 5.1 自定义类型

| token | Python 类 | 说明 |
|---|---|---|
| `ssh_session` | `SSHConnection` | SSH 会话对象；不可文本构造 |

`create_session` 返回 `session: ssh_session`，后续用 `Param.session` 传递。函数参数中的 `session` 不写标准 JSON Schema `type`，而是用 `x-autobranch-type=ssh_session` 标注真实类型；前端会显示为 `ssh_session`，执行时按 `SSHConnection` 校验。LLM 通过变量表和参数描述知道要传 `Param.session`。

### 5.2 函数

| 函数 | 参数 | 返回 |
|---|---|---|
| `ssh.create_session` | `host`, `port?`, `user?`, `pwd?`, `key?`, `timeout?`, `proxy?`, `jump?` | `session: ssh_session`（产出型） |
| `ssh.close_session` | `session: ssh_session` | — |
| `ssh.ssh_exec` | `session: ssh_session`, `command`, `timeout?`, `stdin?`, `interactive?`, `idle_timeout?` | `stdout/stderr/exit_code/channel_id/exited` |
| `ssh.ssh_send` | `session: ssh_session`, `channel_id`, `data`, `newline?` | — |
| `ssh.ssh_read` | `session: ssh_session`, `channel_id`, `idle_timeout?` | `stdout/stderr/exit_code/exited` |
| `ssh.ssh_close_channel` | `session: ssh_session`, `channel_id` | — |
| `ssh.upload_file` | `session: ssh_session`, `file_path`, `remote_path`, `timeout?` | `size/path` |
| `ssh.download_file` | `session: ssh_session`, `remote_path`, `file_path?`, `timeout?` | `size/path` |
| `ssh.upload_dir` | `session: ssh_session`, `dir_path`, `remote_dir`, `timeout?` | `files/path` |
| `ssh.download_dir` | `session: ssh_session`, `remote_dir`, `dir_path?`, `timeout?` | `files/path` |

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

### 6.0 为什么需要文件插件

文件能力分两类，原因不同：

- **工作区读写**：给行为树保存中间结果、配置、日志；
- **文件管理平台**：给浏览器/SSH/前端共享文件，提供目录、路径、MD5、下载链接。

统一走文件管理平台，可以避免浏览器下载目录、SSH 临时目录、前端上传目录三套路径互相隔离。

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

### 7.0 为什么需要 HTTP 插件

很多自动化只需要调 API，不需要打开浏览器：

- 健康检查；
- 创建/查询订单；
- Webhook；
- 后端接口。

浏览器插件也能发请求，但会启动浏览器、依赖页面上下文。`http` 插件更轻量，适合纯 API 场景。

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

## 8. 谓词插件 `predicate`

### 8.0 为什么需要谓词插件

`compute` / `transform` 中有一些返回 bool 的函数，但它们首先服务于数据计算/变换，函数语义和参数并不专为条件表达式设计。

`predicate` 插件提供一组**只返回单个 bool、无副作用**的常用谓词，适合：

- `Step.expect`
- `IfThenElse.if`
- `Branch.when`
- `LoopUntil.until` 的谓词表达式

前端条件编辑器默认展示 `predicate.*`，也允许显示其他单 bool 返回函数。

### 8.1 函数

### 基础比较

| 函数 | 参数 | 返回 |
|---|---|---|
| `predicate.eq` / `ne` | `a`, `b` | `result: bool` |
| `predicate.gt` / `ge` / `lt` / `le` | `a`, `b` | `result: bool` |
| `predicate.between` | `value`, `low`, `high` | `result: bool` |

### 字符串

| 函数 | 参数 | 返回 |
|---|---|---|
| `predicate.contains` / `not_contains` | `value`, `needle`, `ignore_case?` | `result: bool` |
| `predicate.starts_with` / `ends_with` | `value`, `prefix/suffix`, `ignore_case?` | `result: bool` |
| `predicate.matches` | `value`, `pattern`, `ignore_case?` | `result: bool` |
| `predicate.matches_full` | `value`, `pattern`, `ignore_case?` | `result: bool` |
| `predicate.equals_ignore_case` | `a`, `b` | `result: bool` |

### 空值/集合/长度

| 函数 | 参数 | 返回 |
|---|---|---|
| `predicate.is_empty` / `is_not_empty` | `value` | `result: bool` |
| `predicate.is_null` / `is_not_null` | `value` | `result: bool` |
| `predicate.has_key` | `data: object`, `key` | `result: bool` |
| `predicate.has_value` | `data: object`, `value` | `result: bool` |
| `predicate.value_in` / `value_not_in` | `value`, `values: array` | `result: bool` |
| `predicate.length_eq/ge/gt/le/lt` | `value`, `n` | `result: bool` |

示例：

```yaml
if:
  mode: predicate
  expression:
    all:
      - function: predicate.gt
        args: [Param.amount, "0"]
      - function: predicate.le
        args: [Param.amount, "100000"]
      - any:
          - function: predicate.eq
            args: [Param.status, "paid"]
          - not:
              function: predicate.contains
              args: [Param.status, "cancel"]
```

说明：

- 谓词函数错误（如类型不匹配、正则非法）**不等于 false**；
- 错误会让整个条件表达式失败，并记录原因；
- 空 `ALL` / `ANY` 不合法；
- `NOT` 必须恰好一个子条件；
- 谓词函数不写变量，不使用 `save_to`。

## 9. 变量插件 `vars`

### 8.0 有了 `save_to`，为什么还要 `vars.set`

`save_to` 是“把函数返回值写到变量”的协议，但前提是**有一个函数返回值**。

LLM 经常会产生一些“没有对应插件函数”的值：

- 对页面内容做总结；
- 判断风险等级；
- 生成一段命令/URL；
- 把多个信息合并成一条备注。

这时没有 `compute.xxx` / `browser.extract` 之类的函数可调。`vars.set` 提供一个无副作用的“值载体”：

```text
LLM 生成值 → vars.set(value1=值) → save_to=目标变量
```

这样 LLM 直接生成的值也能进入统一的保存、类型校验和报告流程。

### 8.1 什么时候用 `vars.set`

- LLM 自己总结/分类/生成值，且没有插件函数返回它；
- 需要把多个 LLM 结果分别写入多个变量；
- 想避免为“只是存个值”专门开发一个插件。

### 8.2 什么时候不要用 `vars.set`

- 值可以由 `compute` / `transform` / `http` 等确定性函数得到 → 直接用对应函数；
- 固定常量/空容器 → 用 `Define`；
- 值来自 `ref` 子流程 → 用 `ref.returns`。

### 8.3 函数

| 函数 | 参数 | 返回 |
|---|---|---|
| `vars.set` | `value1`, `value2?`, `value3?` | `value1/value2/value3: str`（产出型） |

FunctionCall 示例：

```yaml
n2:
  type: FunctionCall
  function: vars.set
  args: ["hello"]
  returns: {value1: str}
```

在 LLM 叶子中，通常配合 `save_to` 使用：

```text
把页面摘要写入 NewParam.summary:str
```

LLM 会调用 `vars.set(value1="...")`，并通过 `save_to="summary"` 保存。

## 10. 常见问题

### 10.1 为什么浏览器函数不能写进 FunctionCall？

浏览器大量函数是 **LLM-only**（`@llm_function`），因为它们依赖当前页面语义图 `ref` 与上下文。FunctionCall 只支持用户可见函数。

需要 FunctionCall 时可用：

- `browser.open`
- `browser.get_url`
- `browser.scroll`
- `browser.wait`
- `browser.page_request`（支持 `json_body`）
- `browser.get_request_headers`
- `browser.get_header_value`

其他操作请在 Action 描述中让 LLM 执行。

### 10.2 `page_object` / `ssh_session` 能作为树入参吗？

不能直接由文本构造。它们只能：

- 由插件返回；
- 通过 `ref` 传递；
- 在树内用 `Param` 使用。

`GET /api/types` 会显示 `constructible=false`。

### 10.3 `object` 和 `generics` 有什么区别？

- `object`：确定是 Python `dict`；
- `array`：确定是 Python `list`；
- `generics`：不确定类型，任意值；
- 插件自己的对象应声明为自定义类型，而不是 `generics`。

### 10.4 怎样确认函数参数与返回值？

直接调用：

```http
GET /api/functions
GET /api/plugins/{name}/functions
```

前端「插件管理 → 查看函数详情」也会列出参数、返回类型与可见性。
