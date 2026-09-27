# AutoBranch 用户使用说明

> 面向使用者的完整手册：安装部署、参数配置、行为树文档语法、前端编辑器、变量、执行与报告、插件开发、内置插件用法与常见问题。
> 快速上手见 `README.md`；行为树语言契约与模块设计见 `docs/contract.md` / `docs/specs/`。

---

## 1. AutoBranch 是什么

AutoBranch 是**自然语言驱动的行为树自动化工具**。你用 YAML/Dict 写一份**行为树文档**（"做什么、怎么判断、如何循环"），引擎逐叶执行：组合节点（Sequence/IfThenElse/...）是纯程序确定性流转，叶子节点（Action/Condition）由 **LLM agent** 结合页面语义图自主决策调用引擎函数。能力以**插件**注入（浏览器/计算/SSH/文件 + 自定义），执行后产出结构化报告与截图。

核心设计：**流程流转确定，LLM 只在单叶子内行使有限执行权**。

---

## 2. 安装与部署

### 2.1 环境要求

- Python 3.11（推荐 conda/miniforge）
- Node.js 18+（前端）
- Git

### 2.2 后端安装

```bash
conda create -n autobranch python=3.11 -y
conda activate autobranch
pip install -e .            # 以可编辑模式安装本包
```

### 2.3 浏览器依赖（浏览器插件）

浏览器插件基于 Playwright，需安装 Chromium：

```bash
conda run -n autobranch python -m playwright install chromium
```

### 2.4 前端安装

```bash
cd autobranch/frontend
npm install
```

### 2.5 数据库

使用 SQLite 单文件库，后端首次启动自动建库建表（`data/autobranch.db`），无需手动初始化。既有库升级时按需运行迁移脚本（见 §8.7）。

### 2.6 启动

```bash
# 后端（端口 8001，Swagger: http://localhost:8001/docs）
conda run -n autobranch python -m uvicorn autobranch.server.main:app --host 127.0.0.1 --port 8001

# 前端（端口 5174）
cd autobranch/frontend && npm run dev
```

Windows 一键启动：`powershell -ExecutionPolicy Bypass -File .\dev-restart.ps1`（固定 8001/5174，自动探测并停止旧进程）。

> **端口约定**：AutoBranch 固定使用 **8001（后端）/ 5174（前端）**，避开其他项目占用的 8000/5173。

---

## 3. 参数配置

### 3.1 配置文件 `autobranch.config.json`

项目根目录的 `autobranch.config.json`（已 `.gitignore`，含密钥勿提交）：

```json
{
  "llm": {
    "base_url": "https://opencode.ai/zen/go/v1",
    "api_key": "sk-...",
    "model": "deepseek-v4-flash",
    "timeout": 60
  },
  "browser": {
    "browser_type": "chromium",
    "headless": true,
    "timeout_ms": 30000,
    "ignore_https_errors": false
  },
  "run": {
    "timeout": 240,
    "max_rounds": 10,
    "no_progress_rounds": 2,
    "session_timeout": 60,
    "report_dir": "reports"
  },
  "max_concurrent_runs": 3,
  "experience_feedback": true,
  "experience_retention": 5
}
```

| 键 | 说明 | 默认 |
|---|---|---|
| `llm.base_url` | OpenAI 兼容接口地址 | opencode 网关 |
| `llm.api_key` | API 密钥（可留空，用环境变量 `AUTOBRANCH_LLM_API_KEY`） | 空 |
| `llm.model` | 模型名 | deepseek-v4-flash |
| `browser.browser_type` | chromium / firefox / webkit | chromium |
| `browser.headless` | 无头运行 | true |
| `browser.timeout_ms` | 页面操作超时（毫秒） | 30000 |
| `browser.ignore_https_errors` | 关闭 HTTPS 证书校验（内网/私有 CA 用） | false |
| `run.timeout` | 单叶子全局超时（秒，None 不检测） | 240 |
| `run.max_rounds` | 叶子 LLM 工具调用轮数上限 | 10 |
| `max_concurrent_runs` | 后端执行并发上限（超出 FIFO 排队） | 3 |
| `experience_feedback` | 经验回灌开关（关：不采集不注入） | true |
| `experience_retention` | 经验老化：每匹配组保留最近 N 条 | 5 |

### 3.2 环境变量

| 变量 | 说明 |
|---|---|
| `AUTOBRANCH_LLM_API_KEY` | LLM 密钥（优先于配置文件） |
| `AUTOBRANCH_DB_PATH` | SQLite 数据库路径（默认 `data/autobranch.db`） |
| `AUTOBRANCH_REPORT_DIR` | 报告/截图目录（默认 `data/reports`） |
| `AUTOBRANCH_CONFIG` | 配置文件路径（默认项目根 `autobranch.config.json`） |

### 3.3 LLM 请求方式（自动兼容，无需配置）

叶子请求**默认流式**（`stream: true`）；若端点仅接受非流式（响应被拒且提及 `stream`），自动回落非流式并按端点缓存。**无需手动配置**。

### 3.4 浏览器代理路由

代理决策**不写进行为树**，由浏览器插件配置文件控制（类似 Proxy SwitchyOmega）：

- 配置文件：`autobranch/plugins/browser/proxy.config.json`（缺失则不启用路由，浏览器跟随系统代理）；格式示例见 `proxy.config.example.json`。

```json
{
  "default": "system",
  "profiles": {
    "直连": { "mode": "direct" },
    "公司代理": { "server": "http://proxy.corp.example:8080", "username": "u", "password": "p" }
  },
  "rules": [
    { "pattern": "*.corp.example", "proxy": "公司代理" },
    { "pattern": "127.0.0.1", "proxy": "直连" }
  ]
}
```

- `open(url)` 时按 URL 匹配规则（`*` 全部 / `*.域` 子域 / 精确域名），首条命中；无命中走 `default`（system / direct / 具名 profile）。
- 注意事项：
  - 代理在**页面打开时定死**（会话级，页面内跳转不改）；非 per-request。
  - Playwright 强制绕过回环地址（`127.0.0.1`/localhost 不会走代理）。
  - `direct` 模式经独立 `--no-proxy-server` 浏览器承载（用到才启动，多一个浏览器进程）。
  - 改配置后**下次执行生效**（每次 run 装配时读取）。

---

## 4. 使用流程总览

```
书写行为树文档（前端编辑器 或 直接写 YAML）
   → 清晰度校验（保存时/执行前）
   → 点击「执行」（有入参则填参）
   → 引擎确定性遍历：组合节点纯程序流转，叶子走 LLM agent + 插件
   → 执行列表查看进度/状态
   → 执行详情页查看：状态/入参/出参/快照/执行报告/回溯报告/黑板
```

---

## 5. 行为树文档语法（直接书写）

行为树是 YAML 文档，**一文档一树**，三段式：`tree`（文档名）+ `nodes`（节点对象池）+ `root`（根节点引用）。

```yaml
tree: 登录汇总          # 文档名（须 = 保存时的树名）
inputs:                 # 可选：文档级入参声明（名 → 类型）
  user: str
outputs:                # 可选：文档级出参名列表
  - total
nodes:
  n1: {type: Root, name: 根, body: n2}
  n2: {type: Sequence, name: 主流程, actions: [n3, n5]}
  n3: {type: Step, name: 登录, action: n4, expect: 页面出现"登录成功"}
  n4: {type: Action, name: 打开登录, description: 打开页面 "http://...", 输入 admin/secret 点登录}
  n5: {type: FunctionCall, name: 求和, function: compute.add, args: [1, 2], returns: {NewParam.total: int}}
root: n1
```

### 5.1 节点类型与槽位

节点在 `nodes` 下按 id 平铺定义，节点间一切关联经**语义命名槽位字段**引用子树根 id。

| 节点 | 核心语义 | 槽位字段 | 自有字段 |
|---|---|---|---|
| `Root` | 树的根，执行其主体 | `body`（1） | — |
| `Sequence` | 顺序执行，任一失败整体失败 | `actions`（列表） | — |
| `Step` | 操作 + 验证 | `action`（1） | `expect`（条件） |
| `IfThenElse` | 判 `if` 分流 | `then`、`else`（各 1） | `if`（条件） |
| `Branch` | 先操作再按条件分流 | `action`（1）、`branches[].action` | `branches`（[{when,action}\|{otherwise,action}]） |
| `Retry` | 反复执行直到成功 | `body`（1） | `max` |
| `LoopUntil` | 每轮先判条件再执行 | `action`（1） | `until`（条件）、`max` |
| `Action` | 叶子：LLM 执行一个操作 | — | `description` |
| `ref` | 叶子：跨文档调用 | — | `target`、`args`、`returns` |
| `FunctionCall` | 叶子：确定性调用插件函数（不经 LLM） | — | `function`、`args`、`returns` |

**Condition 是概念性节点**（无独立类型），内嵌为字段：`Step.expect`、`IfThenElse.if`、`Branch.branches[].when`、`LoopUntil.until`。条件也是 LLM 叶子（判断真/假）。

### 5.2 变量语法（重点）

- **读取**：`Param.<名>`（叶子执行前被替换为真实值注入 LLM）。
- **写入声明**：`NewParam.<名>[:类型]`（写在叶子 `description` 中，声明该动作可写变量）。
- **`ref`/`FunctionCall` 的 `returns` 接收名必须为 `NewParam.<名>`**（裸键/非 ASCII → 校验错误 `syntax.invalid_return_name`）。
- **变量名仅 ASCII 标识符** `[A-Za-z_][A-Za-z0-9_]*`，不支持中文（`Param.苹果` → `syntax.invalid_name`）。
- 实参（`args`）可为 `Param.x` 或**字面量/常量**，不强制 Param。
- 类型 token：`str` / `int` / `float` / `bool` / `page_ref` / `object`。

```yaml
# 读取 + 写入示例
n3: {type: Action, name: 提取, description: 从表中提取金额写入 NewParam.amount:int}
n4: {type: Step, name: 校验, action: n5, expect: Param.amount 大于 100}
```

### 5.3 `ref` 跨文档调用

`ref` 在运行期动态调用**另一份行为树文档**，`args` 传实参（按序对应被引文档 `inputs`）、`returns` 回收输出（按序对应被引文档 `outputs`）。

```yaml
n2: {type: ref, name: 调用登录, target: 登录文档, args: [Param.user, Param.password],
     returns: {NewParam.loginResult: bool}}
```

- `args` 元素：`Param.x`（读本帧变量）或字面量。
- `returns` 键：`NewParam.<接收名>: 类型`（本树新建变量）。
- 被引文档 `inputs` 与 `args`、`outputs` 与 `returns` 必须数量/顺序对应，否则清晰度校验报错。

### 5.4 FunctionCall 确定性调用

不经 LLM，直接调用插件函数（全名 `插件名.函数名`）。

```yaml
n5: {type: FunctionCall, name: 求和, function: compute.add,
     args: [Param.appleAmt, Param.bananaAmt], returns: {NewParam.total: int}}
```

- `args`：本帧变量或字面量，按序对应函数入参。
- `returns`：接收名（`NewParam.<名>`）→ 类型，按序对应函数多返回值。
- 函数不存在 / 参数不匹配 → 保存/执行前校验 422 拒绝。

### 5.5 完整示例（登录 → 提取 → 求和）

```yaml
tree: 表格求和演示
outputs:
  - total
nodes:
  n1: {type: Root, name: 根, body: n2}
  n2: {type: Sequence, name: 主流程, actions: [n3, n5, n7]}
  n3: {type: Step, name: 登录, action: n4, expect: 页面出现"销售数据表"}
  n4: {type: Action, name: 打开登录,
       description: 打开页面 "http://127.0.0.1:8123/index.html"，输入 admin/secret，点击"登录"按钮}
  n5: {type: Action, name: 提取苹果,
       description: 从"销售数据表"提取"苹果"行的金额，写入变量 NewParam.appleAmt:int}
  n7: {type: FunctionCall, name: 求和, function: compute.add,
       args: [Param.appleAmt, 100], returns: {NewParam.total: int}}
root: n1
```

---

## 6. 前端构建行为树（编辑器）

前端提供**画布式编辑器**（`/editor`）：

- **画布**：节点为卡片，树从根向下生长，兄弟水平排布；分**主树区**（root 可达）与**游离区**（未挂载节点，顶部带「游离」标记）。
- **节点对象池 + 统一槽位**：全部节点定义在 `nodes` 下，节点间关联经**语义命名字段**引用子树根 id（`Root.body`、`Sequence.actions`、`Step.action`、`IfThenElse.then/else`、`Branch.action + branches[].action`、`Retry.body`、`LoopUntil.action`）。槽位下拉**只展示游离树根**（已挂载节点不可选），保证纯树结构。
- **右侧侧栏三个 Tab**：**属性**（选中节点的属性面板）、**节点**（对象池，点击添加为游离树）、**树信息**（树名 + 文档接口 `inputs`/`outputs` 编辑）。
- **节点属性面板**：节点信息（类型/名称）、内部属性分组（槽位/条件/描述/参数）、删除操作。删除语义：删槽位=解引用回游离区；删单节点=子节点各自成游离树；删子树=连带删除后代。
- **文档接口编辑**（树信息 Tab）：编辑 `inputs`（名→类型）与 `outputs`（名列表），ref 参数对齐依据。
- **ref 参数编辑**：选目标文档自动加载其 `inputs`/`outputs` 生成 `args`/`returns` 表单，即时校验对齐/命名冲突/跨文档环。
- **FunctionCall 签名驱动**：选函数后按函数签名自动罗列入参/返回值表单（不手动增删）。
- **即时校验**：必填字段红框标记；保存时汇总校验（单根、无环、槽位存在、无重复引用、ref 目标存在、变量命名规则），并经后端 `/check` 权威兜底。
- **保存/执行**：保存前校验失败阻止保存；执行入口见 §7。

---

## 7. 执行与报告

### 7.1 执行流程

- 树列表点「执行」→ 声明入参则弹**入参对话框**填参（仅可构造类型渲染输入框；含 `page_ref` 等不可构造入参的树**不显示执行按钮**，仅支持 ref 调用）。
- 引擎按**全局并发上限 + FIFO 队列**调度；触发时**冻结行为树快照 + 入参**（执行/重试不随实时树变化）。
- 每个执行是自包含**实例**：快照内容、树名、执行结构指纹、入参、出参。

### 7.2 执行列表页（`/runs`）

展示全部实例：编号、行为树（快照名）、状态（排队中/执行中/成功/失败）、入参、耗时、指纹、开始时间；操作：**查看**（跳转详情）、**重试**（按当时快照+入参）、**删除**（即时刷新）。

### 7.3 执行详情页（`/runs/{id}`）

- 顶部：状态徽章 + 重试 + 返回。
- **实例信息区**：行为树（快照名）、执行状态、指纹、开始/耗时、**入参**、**出参**、折叠的**执行快照**（触发时刻的行为树内容）。
- **执行进度**：进度条、当前节点、已完成节点结果（成功/失败着色 + 截图）。
- **执行报告**：每节点类型/描述/结果/函数调用/判断结果/时间/URL/截图。
- **回溯报告**：每节点 + LLM 输入、推理过程、工具调用序列、最终决策、终止条件。
- **黑板**：当前帧变量快照（路径/类型/值）。

### 7.4 报告内容速览

| 报告 | 内容 |
|---|---|
| 执行报告（exec_report） | 节点结果 + 函数调用 + 判断 + 截图（不含 LLM 推理） |
| 回溯报告（trace_report） | 执行详情 + **LLM 推理**（输入/推理文本/工具调用/决策/终止条件） |

### 7.5 经验回灌

整树成功的历史经验（节点级成功工具调用路径）存入经验库；同条件（同快照 + 同入参 + 同节点）重跑时以"参考而非指令"注入叶子提示词，降低 LLM 随机性导致的重跑失败。配置见 §3.1（`experience_feedback` / `experience_retention`）。

---

## 8. 插件

### 8.1 插件是什么

插件是能力集合（浏览器/计算/SSH/文件/自定义）。行为树叶子经两级能力选择使用：LLM 调用 `use_capability("浏览器")` 加载插件 → 其函数进入工具集供细选。**函数标识 = 全名 `插件名.函数名`**（跨插件可同名）。FunctionCall 节点直接以全名确定性调用。

### 8.2 内置插件与函数

| 插件 | 函数 |
|---|---|
| **browser** | `open` `activate` `get_url` `click` `type` `select` `check` `uncheck` `scroll` `wait` `download` `upload` `extract` `semantic_graph` `http_request` `get_response` `clear_requests` |
| **compute** | `add` `compare` `multiply` `sort` `sum` |
| **ssh** | `create_session` `ssh_exec` `close_session` |
| **file** | `read` `write` `diff` |

**浏览器插件代理配置**：见 §3.4（`proxy.config.json`）。

### 8.3 编写自定义插件

前端「插件管理」页编写 Python 源码（CodeMirror 编辑器），保存即校验并重载。**约束**：仅用 Python 标准库；不得 import 其他插件 / `common` / 三方库；不得直接写变量空间（返回值由引擎落笔）。

```python
class Demo(PluginBase):
    name = "demo"
    description = "演示插件"

    @engine_function(name="double", description="翻倍", parameters={"required": [], "properties": {}})
    def double(self):
        return 42

plugin = Demo()
```

- `@engine_function` 标注的函数才会注册（键 = 全名 `demo.double`）。
- 函数返回普通值或 `FunctionResult`（可带 `values` / `report` 附加信息）。
- 产出型函数可声明 `output_param`（单一变量目标参数），由引擎落笔写变量。

### 8.4 函数清单查看

`GET /api/functions` 返回全部已注册函数（全名 + 结构化定义），前端函数选择器据此渲染。

---

## 9. 常见问题

- **LLM 接口只支持流式 / 只支持非流式**：已自动兼容，无需配置。
- **访问自签/私有 CA 站点报证书错误**：设置 `browser.ignore_https_errors: true`（仅内网）。
- **访问某些站点需要代理**：配置浏览器代理路由（§3.4）。
- **`ERR_CERT_AUTHORITY_INVALID`**：同证书豁免。
- **前端 5174 / 后端 8001 端口冲突**：AutoBranch 固定用 8001/5174，与 8000/5173 无关。
- **执行失败排查**：查看详情页的失败原因（指向首个失败叶子）与回溯报告（LLM 决策过程）。

---

## 附：快速参考

- 节点类型：`Root` `Sequence` `Step` `IfThenElse` `Branch` `Retry` `LoopUntil` `Action` `ref` `FunctionCall`
- 变量：`Param.x`（读） / `NewParam.x[:type]`（写） / `returns` 键必须 `NewParam.<ASCII名>`
- 类型：`str` `int` `float` `bool` `page_ref` `object`
- 配置：`autobranch.config.json`（llm/browser/run/并发/经验）+ `browser/proxy.config.json`（代理）
- 端口：后端 8001，前端 5174