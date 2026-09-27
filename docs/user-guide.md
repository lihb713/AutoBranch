# AutoBranch 用户使用说明（完整版）

> 面向第一次使用 AutoBranch 的用户。假设你**从未用过**本工具：本文从"这是什么"开始，一步步教你安装、配置、写行为树、用前端编辑器、执行、看报告、写插件，以及所有支持的使用细节。遇到问题时查最后的「常见问题」。
>
> 快速上手（一页版）见 `README.md`；行为树语言契约与模块设计见 `docs/contract.md` / `docs/specs/`。

---

## 目录

1. [AutoBranch 是什么](#1-autobranch-是什么)
2. [核心概念速成](#2-核心概念速成)
3. [安装与部署](#3-安装与部署)
4. [配置](#4-配置)
5. [前端界面导航](#5-前端界面导航)
6. [行为树文档语法（直接书写）](#6-行为树文档语法直接书写)
7. [前端编辑器：可视化构建行为树](#7-前端编辑器可视化构建行为树)
8. [变量详解](#8-变量详解)
9. [执行与报告](#9-执行与报告)
10. [内置插件与函数详解](#10-内置插件与函数详解)
11. [自定义插件开发](#11-自定义插件开发)
12. [浏览器代理路由配置（详解）](#12-浏览器代理路由配置详解)
13. [经验回灌](#13-经验回灌)
14. [常见问题与排查](#14-常见问题与排查)
15. [附录：快速参考](#15-附录快速参考)

---

## 1. AutoBranch 是什么

AutoBranch 是一个**自然语言驱动的行为树自动化工具**。你不需要写代码，只需要用 **YAML 文本**（或前端可视化编辑器）写一份"行为树文档"，描述：**做什么**（打开页面、点击按钮、输入文字）、**怎么判断**（页面上是否出现某内容）、**如何循环**（重试直到成功、循环翻页）。

引擎拿到这份文档后：

- **组合节点**（Sequence/IfThenElse/Branch/Retry/LoopUntil…）由**程序确定性**执行——不会出错，也不依赖 AI；
- **叶子节点**（Action 操作 / Condition 判断）由 **LLM（大模型）**结合浏览器"语义图"自主决定如何调用引擎函数——这就是"自然语言驱动"；
- 执行全程记录节点结果与截图，产出**执行报告**与**回溯报告**。

它能操作浏览器（网页自动化），也能调用计算、SSH、文件等插件，还支持你编写自定义插件——所以是**通用的自动化执行平台**，不止于网页。

---

## 2. 核心概念速成

| 概念 | 一句话 | 详细 |
|---|---|---|
| 行为树文档 | 一份 YAML 文本，`tree/nodes/root` 三段式 | §6 |
| 节点 | 组合节点（流转）或叶子（Action/Condition/ref/FunctionCall） | §6.1 |
| 变量 | `Param.x` 读、`NewParam.x[:类型]` 写 | §8 |
| 入参/出参 | 文档级 `inputs`（外部传入）、`outputs`（对外返回） | §6.5 |
| 插件 | 能力集合（浏览器/计算/SSH/文件/自定义），函数以 `插件名.函数名` 标识 | §10/§11 |
| 执行实例 | 一次执行 = 自包含实例（快照 + 入参 + 出参） | §9 |
| 报告 | 执行报告（节点结果+截图）/ 回溯报告（含 LLM 推理） | §9.5 |

**最重要的一条规则**：行为树文档中，**变量名只支持 ASCII 标识符**（`[A-Za-z_][A-Za-z0-9_]*`，不支持中文）；所有变量引用/声明用 `Param.` / `NewParam.` 语法。违反会在保存/执行前被校验拒绝。

---

## 3. 安装与部署

### 3.1 环境要求

- **Python 3.11**（推荐用 conda/miniforge 建独立环境，避免污染系统）
- **Node.js 18+**（前端界面）
- **Git**（克隆代码）

### 3.2 克隆并安装后端

```bash
git clone git@github.com:lihb713/AutoBranch.git
cd AutoBranch

# 1) 创建独立 conda 环境
conda create -n autobranch python=3.11 -y
conda activate autobranch

# 2) 安装依赖 + 以可编辑模式安装本包
pip install -e .
```

> 已有环境则直接 `conda activate autobranch && pip install -e .` 即可。

### 3.3 安装浏览器（浏览器插件依赖）

浏览器插件基于 Playwright，需要下载 Chromium（一次即可）：

```bash
conda run -n autobranch python -m playwright install chromium
```

### 3.4 安装前端

```bash
cd autobranch/frontend
npm install
```

### 3.5 数据库

后端使用 **SQLite 单文件库**（`data/autobranch.db`），**首次启动自动创建**，无需手动初始化。

### 3.6 启动

```bash
# 后端（端口 8001，API 文档 http://localhost:8001/docs）
conda run -n autobranch python -m uvicorn autobranch.server.main:app --host 127.0.0.1 --port 8001

# 前端（端口 5174），另开一个终端
cd autobranch/frontend && npm run dev
```

浏览器打开 `http://localhost:5174` 即可使用。

**Windows 一键启动**：项目根执行

```powershell
powershell -ExecutionPolicy Bypass -File .\dev-restart.ps1
```

脚本会自动：停掉旧进程 → 启动后端 8001 → 启动前端 5174 → 等待健康检查通过。

> **端口约定**：AutoBranch **固定使用 8001（后端）/ 5174（前端）**，与其他项目占用的 8000/5173 无关。请不要在别处占用这两个端口。

### 3.7 验证安装成功

- 后端健康检查：浏览器打开 `http://localhost:8001/api/health`，返回 `{"status":"ok"}`。
- 前端：打开 `http://localhost:5174`，能看到「行为树」页面。

---

## 4. 配置

AutoBranch 的配置来源：**配置文件 `autobranch.config.json`（项目根）** + **环境变量** + **浏览器插件代理配置文件**。

### 4.1 主配置文件 `autobranch.config.json`

该文件已加入 `.gitignore`（含密钥，勿提交）。**不存在也能运行**（用默认值）。

完整结构：

```json
{
  "llm": {
    "base_url": "https://opencode.ai/zen/go/v1",
    "api_key": "",
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
    "initial_graph_scope": "full",
    "initial_graph_lod": 2,
    "report_dir": "reports",
    "page_var": "page",
    "budget_limit": null
  },
  "max_concurrent_runs": 3,
  "experience_feedback": true,
  "experience_retention": 5
}
```

各键说明：

**`llm`（大模型）**

| 键 | 说明 | 默认 |
|---|---|---|
| `base_url` | OpenAI 兼容接口地址（`/chat/completions` 会自动拼） | opencode 网关 |
| `api_key` | 密钥（可留空，用环境变量 `AUTOBRANCH_LLM_API_KEY`） | 空 |
| `model` | 模型名 | deepseek-v4-flash |
| `timeout` | 单次 LLM 请求超时（秒） | 60 |

**`browser`（浏览器）**

| 键 | 说明 | 默认 |
|---|---|---|
| `browser_type` | chromium / firefox / webkit | chromium |
| `headless` | 无头运行（不弹浏览器窗口） | true |
| `timeout_ms` | 页面元素操作超时（毫秒） | 30000 |
| `ignore_https_errors` | 关闭 HTTPS 证书校验（内网/私有 CA 站点用，见 §14） | false |

**`run`（引擎运行）**

| 键 | 说明 | 默认 |
|---|---|---|
| `timeout` | 单叶子全局超时（秒；`null` 不检测） | 240 |
| `max_rounds` | 叶子 LLM 工具调用轮数上限 | 10 |
| `no_progress_rounds` | 连续几轮无进展判定为失败 | 2 |
| `session_timeout` | 单次 LLM 请求超时（秒） | 60 |
| `initial_graph_scope` | 初始语义图范围（full） | full |
| `initial_graph_lod` | 初始语义图细节级别 0~3 | 2 |
| `report_dir` | 报告/截图目录 | reports |
| `budget_limit` | 语义图 token 预算（null 不检测） | null |

**顶层**

| 键 | 说明 | 默认 |
|---|---|---|
| `max_concurrent_runs` | 后端同时最多执行的实例数，超出**进 FIFO 队列** | 3 |
| `experience_feedback` | 经验回灌开关（关：不采集不注入） | true |
| `experience_retention` | 经验老化：每匹配组保留最近 N 条 | 5 |

### 4.2 环境变量

| 变量 | 说明 |
|---|---|
| `AUTOBRANCH_LLM_API_KEY` | LLM 密钥（**优先于配置文件**） |
| `AUTOBRANCH_DB_PATH` | SQLite 数据库路径（默认 `data/autobranch.db`） |
| `AUTOBRANCH_REPORT_DIR` | 报告/截图目录（默认 `data/reports`） |
| `AUTOBRANCH_CONFIG` | 配置文件路径（默认项目根 `autobranch.config.json`） |

### 4.3 LLM 请求方式（自动，无需配置）

叶子请求**默认流式**（`stream: true`）。若你接的接口**只接受非流式**（响应被拒且错误信息含 "stream"），工具自动回落非流式并按端点记忆，**之后不再重试**。因此对接任意 OpenAI 兼容端点都无需配置。

### 4.4 行为树文档内配置覆盖

你可以在**行为树文档顶层**（与 `tree` 同级）写三个保留键，覆盖本文档及 ref 子树的运行参数：

```yaml
tree: 登录
timeout: 30        # 本文档叶子超时（秒）
retry: 3           # 重试次数
browser: chromium  # 浏览器类型
```

不写则用全局配置默认。

---

## 5. 前端界面导航

前端顶部有**三个页签**（全局导航）：

| 页签 | 地址 | 用途 |
|---|---|---|
| **行为树管理** | `/` | 行为树列表、导入/新建、编辑/执行/删除 |
| **行为树执行列表** | `/runs` | 所有执行实例（进行中/历史），查看/重试/删除 |
| **插件管理** | `/plugins` | 查看/编辑/新增/删除插件 |

（编辑器页 `/editor`、执行详情页 `/runs/{id}` 通过点击进入，不占页签。）

---

## 6. 行为树文档语法（直接书写）

行为树是 YAML，**一文档一树**。三段式：

```yaml
tree: 文档名          # 必须 = 保存时的树名
nodes:                # 节点对象池：所有节点按 id 平铺
  n1: {...}
  n2: {...}
root: n1              # 根节点引用（必须指向 type: Root）
```

可选顶层键：`inputs`（入参声明）、`outputs`（出参名）、`timeout`/`retry`/`browser`（配置覆盖）。

### 6.1 节点类型与字段

| 节点 | 干什么 | 槽位字段（挂子树） | 自有字段 |
|---|---|---|---|
| `Root` | 树的根，执行其主体 | `body`（1） | — |
| `Sequence` | 顺序执行，任一失败则整体失败 | `actions`（列表，有序） | — |
| `Step` | 做一步并验证（操作 + 条件） | `action`（1） | `expect`（条件文本） |
| `IfThenElse` | 按条件分流 | `then`（1）、`else`（1） | `if`（条件文本） |
| `Branch` | 先做前置操作，再按条件分流 | `action`（1）、`branches[].action` | `branches`（见下） |
| `Retry` | 失败则重试，直到成功或到上限 | `body`（1） | `max`（最多轮数） |
| `LoopUntil` | 每轮先判条件，满足则退出，否则执行循环体 | `action`（1） | `until`（条件）、`max` |
| `Action` | 叶子：LLM 执行一个自然语言操作 | — | `description` |
| `ref` | 叶子：调用另一份行为树文档 | — | `target`/`args`/`returns` |
| `FunctionCall` | 叶子：确定性调用插件函数（不经 LLM） | — | `function`/`args`/`returns` |

**条件（Condition）没有独立类型**，内嵌为字段：`Step.expect`、`IfThenElse.if`、`Branch.branches[].when`、`LoopUntil.until`。条件也是 LLM 叶子（判断真/假）。

**Branch 的 `branches` 写法**：

```yaml
n3:
  type: Branch
  action: n4                  # 先执行的前置操作（如提取金额）
  branches:
    - when: 金额大于100        # 条件为真 → 执行 n5
      action: n5
    - otherwise: n6            # 都不满足 → 执行 n6
```

### 6.2 各种节点示例

```yaml
# Sequence 顺序执行
n2: {type: Sequence, actions: [n3, n4, n5]}

# Step：操作 + 验证
n3: {type: Step, action: n4, expect: 页面出现"登录成功"}
n4: {type: Action, description: 输入用户名 admin}

# IfThenElse：按条件分流
n5: {type: IfThenElse, if: 页面有"已批准", then: n6, else: n7}

# Retry：失败重试，最多 2 次
n8: {type: Retry, body: n9, max: 2}

# LoopUntil：循环直到条件成立，最多 3 轮
n10: {type: LoopUntil, action: n11, until: 出现"下一页"按钮, max: 3}

# Action 叶子（LLM 执行）
n12: {type: Action, description: 打开页面 "https://example.com"，点击"登录"按钮}

# ref 跨文档调用
n13: {type: ref, target: 登录文档, args: [Param.user, Param.pass],
      returns: {NewParam.loginOk: bool}}

# FunctionCall 确定性调用
n14: {type: FunctionCall, function: compute.add, args: [Param.a, 2],
      returns: {NewParam.total: int}}
```

### 6.3 `ref` 跨文档调用（把另一份树当子程序）

`ref` 在运行期动态加载**另一份行为树文档**并执行：

```yaml
n13:
  type: ref
  target: 登录文档          # 被调用的文档名（须存在）
  args: [Param.user, "admin"]   # 实参，按序对应被调文档的 inputs；可为变量或字面量
  returns: {NewParam.loginOk: bool}   # 回收被调文档 outputs，键必须 NewParam.<名>
```

- 被调文档的 `inputs` 数量/顺序 与 `args` 必须一致；`outputs` 与 `returns` 一致。
- `returns` 键 = 本树新建变量（`NewParam.<ASCII名>: 类型`）。

### 6.4 `FunctionCall` 确定性调用（不经 LLM）

直接调用插件函数，结果确定、速度快：

```yaml
n14:
  type: FunctionCall
  function: compute.add       # 全名：插件名.函数名
  args: [Param.a, 2]          # 实参：本帧变量或字面量，按序对应函数入参
  returns: {NewParam.total: int}   # 接收名（NewParam.<ASCII名>）→ 类型
```

- 函数不存在 / 参数数量不匹配 → 保存或执行前 422 拒绝。
- 常用函数见 §10。

### 6.5 文档级入参 / 出参

```yaml
tree: 订单
inputs:
  user: str          # 入参：名 → 类型（str/int/float/bool/page_ref/object）
  amount: int
outputs:
  - result           # 出参：名列表（执行后对外返回）
nodes: ...
```

- **入参**：执行时由外部提供（前端弹框填写或 API 传入）；叶子用 `Param.user` 读取。
- **出参**：执行结束后引擎读根帧，报告页/执行列表展示。
- **不可由文本构造的入参类型**（如 `page_ref`）：前端不显示"执行"按钮，该树**只能被其他树 `ref` 调用**（调用方在运行期提供页面对象）。

### 6.6 一个完整可执行示例

```yaml
tree: 表格求和演示
outputs:
  - total
nodes:
  n1: {type: Root, name: 根, body: n2}
  n2: {type: Sequence, name: 主流程, actions: [n3, n5]}
  n3: {type: Step, name: 登录, action: n4, expect: 页面出现"销售数据表"}
  n4:
    type: Action
    name: 打开登录
    description: 打开页面 "http://127.0.0.1:8123/index.html"，输入 admin/secret，点击"登录"按钮
  n5:
    type: FunctionCall
    name: 求和
    function: compute.add
    args: [1, 2]
    returns: {NewParam.total: int}
root: n1
```

---

## 7. 前端编辑器：可视化构建行为树

打开「行为树管理」→ 点「新建行为树」进入编辑器 `/editor`。

### 7.1 界面布局

- **画布**（左侧）：节点卡片，根在上、向下生长、兄弟水平排布；分**主树区**（root 可达）与**游离区**（未挂载的节点，顶部标「游离」）。
- **右侧侧栏**三个 Tab：
  - **属性**：选中节点的属性面板（默认）
  - **节点**：节点对象池，点击「+」把新节点加为游离树
  - **树信息**：树名 + 文档接口（`inputs`/`outputs`）

### 7.2 常见操作（点击路径）

| 我想… | 操作 |
|---|---|
| 加一个节点 | 「节点」Tab → 选类型（Action/Sequence/Step/…）→ 点添加 → 出现在游离区 → 自动切到「属性」填内容 |
| 把节点挂进槽位 | 选中父节点 → 「属性」里对应槽位（如 Sequence.actions / Step.action）→ 下拉选择**游离树根** |
| 修改节点内容 | 点击画布节点 → 「属性」Tab 填字段（描述/条件/max…） |
| 改树名/文档接口 | 「树信息」Tab |
| 删除节点 | 选中节点 → 「属性」底部「删除此节点」/「删除子树」 |
| 添加 ref 引用 | 建 ref 节点 → 「属性」选目标文档 → 自动生成 args/returns 表单 |
| 添加 FunctionCall | 建 FunctionCall 节点 → 「属性」选函数 → 按签名自动生成入参/返回值表单 |

### 7.3 删除语义（务必理解）

- **删槽位** = 解引用：该子节点回到游离区。
- **删单节点** = 它的各槽位子节点各自成为游离树。
- **删子树** = 连带删除全部后代。
- **删 ref** = 仅解除引用，被引用文档不受影响。

### 7.4 校验

- 节点必填字段（如 Action.description、Step.expect、IfThenElse.if/then/else 等）未填 → 红框标记。
- 保存时汇总校验：单根、槽位引用存在且无重复、无环（含跨文档环）、ref 目标存在、变量命名规则（ASCII + NewParam）。
- 校验失败会阻止保存并给出可读错误清单；后端 `/check` 权威兜底。

### 7.5 导入 / 导出

「行为树管理」页有「导入文档」（选择 `.yaml/.yml/.md/.txt` 文件，自动解析树名）与「新建行为树」；也可直接在列表行点「编辑」进入已有树。

---

## 8. 变量详解

### 8.1 读取：`Param.x`

写在叶子描述中，引擎在执行前从帧内读取真实值替换后注入 LLM：

```yaml
n3: {type: Action, description: 在搜索框输入 Param.keyword 并回车}
```

- 读取的变量必须是：文档 `inputs` 声明、文档内某处 `NewParam.x` 声明、或 `ref` 的 `returns` 目标。否则清晰度校验报 `scope.get_undeclared`。
- 未定义的读取 → 该叶子直接 FAILURE（程序错误）。

### 8.2 写入：`NewParam.x[:类型]`

声明"本动作会把结果存到变量 x"（LLM 决定何时调用 extract/产出型工具）：

```yaml
n5: {type: Action, description: 从表中提取金额写入 NewParam.amount:int}
```

- 类型 token：`str` / `int` / `float` / `bool` / `page_ref` / `object`（可省略，按动作推断）。
- 产出型工具的目标必须在 `NewParam.` 声明集内，否则拒绝写入。

### 8.3 命名规则（强制）

- 变量名 **ASCII 标识符** `[A-Za-z_][A-Za-z0-9_]*`，**不支持中文**。
- `ref` / `FunctionCall` 的 `returns` 接收名必须 `NewParam.<名>`（裸键 → 校验错误）。
- `args` 实参可为变量或字面量，不强制 Param。

### 8.4 类型

| token | 含义 |
|---|---|
| `str` / `int` / `float` / `bool` | 基础标量 |
| `page_ref` | 页签引用（只能由引擎 `open` 产生，不能由文本构造） |
| `object` | 泛型对象（页面对象/会话/文件句柄等插件对象） |

### 8.5 变量从哪里来

- **入参**：文档 `inputs` 声明 → 执行时由外部提供 → 叶子 `Param.x` 读取。
- **叶子产出**：`NewParam.x[:类型]` 声明 → LLM 调产出型工具（如 `extract`）写入。
- **ref 回收**：被调文档的 `outputs` 经 `returns` 写入本帧。
- **FunctionCall 回收**：插件函数多返回值经 `returns` 写入。

---

## 9. 执行与报告

### 9.1 触发执行

「行为树管理」列表每行有「执行」按钮：

- **无入参** → 直接执行。
- **有可构造入参**（str/int/float/bool）→ 弹出入参对话框填值后执行。
- **含不可构造入参**（如 `page_ref`）→ **不显示**执行按钮（该树仅能 ref 调用）。

### 9.2 执行机制

- 触发时引擎**冻结行为树内容快照 + 入参**（之后修改树不影响本次执行）。
- 按**全局并发上限 + FIFO 队列**调度；并发满则排队（列表显示"排队中"）。
- 每个执行是一个**自包含实例**：快照内容、快照树名、执行结构指纹、入参、出参。
- 删除行为树后，其历史执行实例**保留**（可回看/重试）。

### 9.3 执行列表（`/runs`）

| 列 | 内容 |
|---|---|
| # | 实例编号 |
| 行为树 | 快照树名（点击进入详情） |
| 状态 | 排队中 / 执行中 / 成功 / 失败 |
| 入参 | JSON 展示本次入参 |
| 耗时 | 执行用时 |
| 指纹 | 执行结构指纹（短哈希） |
| 开始时间 | — |
| 操作 | **查看**（跳详情）、**重试**（按当时快照+入参）、**删除**（即时刷新） |

进行中的实例会自动轮询刷新。

### 9.4 执行详情页（`/runs/{id}`）

- **顶部**：状态徽章 + 「重试」 + 「返回执行列表」。
- **实例信息区**：行为树（快照名）、执行状态、指纹、开始/耗时、**入参**、**出参**、折叠的**执行快照**（点击展开，显示触发时刻的行为树内容）。
- **执行进度**：进度条 + 当前节点 + 已完成节点（成功/失败着色，Action 附截图）。
- **执行报告 / 回溯报告** 切换查看。
- **黑板**：当前帧变量快照（路径/类型/值）。

### 9.5 报告内容

| 报告 | 内容 |
|---|---|
| **执行报告**（exec_report） | 每个节点的类型/描述/结果、函数调用、判断结果、时间、页面 URL、截图路径 |
| **回溯报告**（trace_report） | 每个节点的 LLM 输入、**推理过程**、**工具调用序列**（函数/参数/结果）、最终决策、终止条件 |

看"为什么这么走"，看回溯报告；看"结果如何"，看执行报告。

### 9.6 重试 / 删除

- **重试**：复制该实例的快照+入参新建执行（跑的是**当时的内容**，不是树的最新版本）。
- **删除**：删除实例并清理其报告目录；删除行为树保留历史。

---

## 10. 内置插件与函数详解

插件通过 **`use_capability("插件名")`** 由 LLM 加载（能力概览在叶子系统提示中），或由 FunctionCall 直接以全名调用。函数标识 = `插件名.函数名`。

### 10.1 浏览器插件 `browser`

页面对象用 `open` 返回（泛型 `object` 可存变量），元素引用 `ref`（如 `[1]`）来自最近一次 `semantic_graph`（**每次语义图生成后旧 ref 失效**，需重新获取）。

| 函数 | 参数 | 说明 |
|---|---|---|
| `open` | `url`（可 `save_to` 存页面对象） | 打开 URL 新建页签并设为当前活动页 |
| `activate` | `page`（页面对象） | 切换已有页签为活动页 |
| `get_url` | （产出型，`save_to`） | 取当前活动页 URL 字符串 |
| `semantic_graph` | `scope`（full 或区域 id）、`lod`（0~3） | 生成当前页语义图（"看页面"），同时截图 |
| `click` | `ref` | 点击元素 |
| `type` | `ref`、`text` | 向输入框输入文本（替换现有值） |
| `select` | `ref`、`option` | 下拉选择（优先文本匹配，其次 value） |
| `check` / `uncheck` | `ref` | 勾选/取消勾选 checkbox/radio |
| `scroll` | `direction`（up/down/left/right/top/bottom） | 滚动页面 |
| `wait` | `condition`（`selector: <CSS>` / `text: <文本>` / `url: <子串>`） | 等待条件满足 |
| `extract` | `ref`（产出型，`target`） | 提取元素值并写入目标变量 |
| `download` | `ref` | 触发下载并保存 |
| `upload` | `ref`、`path` | 上传本地文件到文件控件 |
| `http_request` | `method`、`url`、`headers`、`body` | 发起独立 HTTP 请求（不经页面，认证走 headers） |
| `get_response` | `method`、`url_pattern`（`*` 通配） | 读页面已发生的匹配请求响应 |
| `clear_requests` | — | 清空页面请求记录 |

**LLM 叶子怎么用浏览器**：你只需在 `description` 里用自然语言说"打开页面 X，点击登录，输入 admin"——LLM 会自动：`semantic_graph` 看页面 → 用 `ref` 定位 → 调 `click`/`type`。不用手写函数调用。

**浏览器代理配置**：见 §12。

### 10.2 计算插件 `compute`

| 函数 | 参数 | 返回 |
|---|---|---|
| `add` | `a`、`b` | 两数之和 |
| `multiply` | `a`、`b` | 两数之积 |
| `compare` | `a`、`b` | `a > b` 布尔结果 |
| `sort` | `data`（列表）、`desc`（可选） | 排序后的列表 |
| `sum` | `values`（列表） | 求和 |

FunctionCall 示例：`function: compute.add, args: [Param.a, 2], returns: {NewParam.total: int}`。

### 10.3 SSH 插件 `ssh`

| 函数 | 参数 | 说明 |
|---|---|---|
| `create_session` | `host`、`port`（默认22）、`user`、`pwd`/`key` 二选一、`timeout` | 建 SSH 会话（返回会话对象） |
| `ssh_exec` | `session`、`command`、`timeout` | 执行命令，返回 stdout/stderr/exit_code（非零退出码为失败） |
| `close_session` | `session` | 关闭会话 |

> 依赖 `paramiko`，未安装时调用返回"paramiko 未安装"。

### 10.4 文件插件 `file`

| 函数 | 参数 | 说明 |
|---|---|---|
| `read` | `path` | 读文件内容（UTF-8，>10MB 拒绝） |
| `write` | `path`、`content` | 写文件（覆盖） |
| `diff` | `file_a`、`file_b` | 对比两个文件，返回是否相同与差异 |

> 相对路径以引擎工作目录为基址。

### 10.5 函数清单查看

`GET http://localhost:8001/api/functions` 返回全部已注册函数（全名 + 结构化定义），前端函数选择器也据此渲染。

---

## 11. 自定义插件开发

### 11.1 写在哪里

前端「插件管理」页 → 「新增插件」→ CodeMirror 编辑器写 Python 源码 → 保存即校验并生效。

### 11.2 约束

- **仅用 Python 标准库**（不得 import 三方库、其他插件、`common`）。
- 不得直接写变量空间（返回值由引擎落笔）。
- 插件名唯一（不得与内置插件同名）。

### 11.3 基本结构

```python
class Demo(PluginBase):
    name = "demo"
    description = "演示插件"

    @engine_function(
        name="double",
        description="翻倍",
        parameters={"type": "object", "properties": {"x": {"type": "number"}}, "required": ["x"]},
        returns=("result",),
    )
    def double(self, x: float) -> float:
        return x * 2

plugin = Demo()
```

- **只有 `@engine_function` 标注的函数才注册**，键 = 全名 `demo.double`。
- 函数返回普通值，或 `FunctionResult`（可带 `values` / `report` 附加信息）。
- 产出型函数：`output_param` 声明单一变量目标参数（如 `extract` 的 `target`），引擎落笔写变量。
- `init(runtime)` 可选：初始化插件公共资源；`release()` 释放（运行结束统一调用）。
- 可依赖 `common` 共享库（预置插件；自定义插件不允许）。

### 11.4 删除插件

删除插件时若被行为树引用，前端弹窗提示，并**把引用其函数的行为树 FunctionCall 引用置空**。

---

## 12. 浏览器代理路由配置（详解）

### 12.1 为什么需要

访问某些网站需要走特定代理（公司内网代理、专用出口、或必须直连绕过系统代理）。AutoBranch 让**代理决策不写进行为树**，而是由浏览器插件的配置文件按"哪个站点走哪个代理"自动匹配。

### 12.2 配置文件位置

```
autobranch/plugins/browser/proxy.config.json
```

（该文件不入库，由运维/你自己创建；格式示例见同目录 `proxy.config.example.json`。）

**文件不存在 → 不启用代理路由**，浏览器跟随系统代理（默认行为）。

### 12.3 配置格式

```json
{
  "default": "system",
  "profiles": {
    "直连":     { "mode": "direct" },
    "公司代理":  { "server": "http://proxy.corp.example:8080",
                 "username": "u", "password": "p" }
  },
  "rules": [
    { "pattern": "*.corp.example", "proxy": "公司代理" },
    { "pattern": "*.intranet",     "proxy": "直连" },
    { "pattern": "127.0.0.1",      "proxy": "直连" }
  ]
}
```

**三部分**：

1. **`default`**：兜底模式——`"system"`（跟随系统代理）/ `"direct"`（直连）/ 某个 profile 名字。
2. **`profiles`**：可复用的代理定义，三种形态：
   - `{"mode": "system"}`：跟随系统代理；
   - `{"mode": "direct"}`：直连（不走任何代理）；
   - `{"server": "http://host:port", "username": ..., "password": ...}`：自定义代理（支持 HTTP/HTTPS/SOCKS5，可带凭据）。
3. **`rules`**：站点 → 代理的规则列表，**按顺序匹配，首条命中生效**：
   - `"*"`：匹配所有域名；
   - `"*.corp.example"`：匹配 `corp.example` 及其任意子域（`a.corp.example` 等）；
   - `"corp.example"`：精确匹配该域名；
   - `"127.0.0.1"`：精确匹配该 IP。

### 12.4 生效时机

`open(url)` 打开页面时，引擎按 URL 匹配规则选择代理并打开在对应会话中。**改配置文件后，下次执行生效**（每次 run 装配时读取）。

### 12.5 三条重要限制（务必知道）

1. **代理在页面打开时定死**：代理是"会话（context）级"，不是每个请求可切换。页面打开后内部跳转到其他域名，仍走原代理。需要 per-request 切换的场景（如 SwitchyOmega 那样按请求分流）当前不支持。
2. **回环地址永远绕过代理**：`127.0.0.1` / `localhost` 不会走代理（Playwright 强制 `<-loopback>` 绕过）。所以本地测试页不需要代理规则，配了也不生效。
3. **`direct` 模式用独立浏览器承载**：直连需要一个单独的 `--no-proxy-server` 浏览器进程（用到时才启动，会多占一个浏览器进程的内存）。

### 12.6 示例场景

- 公司内网站点 `*.intranet` → 走 `direct`（内网直连，不绕出口代理）。
- 外部业务 `*.corp.example` → 走公司代理（带账号）。
- 其余 → `system`（跟随系统代理）。

---

## 13. 经验回灌

### 13.1 是什么

同一棵行为树**成功执行一次**后，引擎会保存每个叶子节点的"成功做法"（工具调用路径）到经验库。之后**同条件**（同行为树快照 + 同入参 + 同节点）重跑时，把上次成功的做法以"参考而非指令"注入叶子提示词，帮助 LLM 更稳定，降低因 LLM 随机性导致的重跑失败。

### 13.2 配置

| 键 | 默认 | 说明 |
|---|---|---|
| `experience_feedback` | true | 关闭则不采集也不注入 |
| `experience_retention` | 5 | 每个匹配组只保留最近 5 条经验（自动老化） |

### 13.3 机制要点

- 只从**整树成功**的 run 采集；失败 run 不采。
- 树内容修改、入参变化 → 经验自动不匹配（不注入，避免误导）。
- 经验是**蒸馏后的成功路径**（去掉了 ref 编号等运行时标识），注入时明示"仅供参考，以当前语义图为准"。

---

## 14. 常见问题与排查

| 问题 | 解决 |
|---|---|
| 打开 HTTPS 站点报 `ERR_CERT_AUTHORITY_INVALID` | `browser.ignore_https_errors: true`（仅内网/私有 CA；会信任所有证书） |
| 站点需走代理 / 直连 | 配置浏览器代理路由（§12） |
| LLM 接口只支持流式 / 只支持非流式 | 已自动兼容，无需配置 |
| 执行失败 | 详情页看失败原因（指向首个失败叶子）+ 回溯报告（LLM 决策过程） |
| 保存报 `syntax.invalid_return_name` | `returns` 键要用 `NewParam.<名>`，不能裸键/中文 |
| 保存报 `syntax.invalid_name` | 变量名用了中文/非 ASCII；变量名只能是 ASCII 标识符 |
| 排队中一直不执行 | 并发上限（`max_concurrent_runs`）满了，等前面的结束自动调度 |
| 端口 5174 / 8001 被占 | AutoBranch 固定用这两个；检查是否被其他程序占用并释放 |
| 浏览器插件报"浏览器未装配" | 叶子要先 `use_capability("browser")` 或行为树用到浏览器能力 |
| `ref` 找不到目标文档 | 确认被调文档名存在且 `target` 拼写正确 |

---

## 15. 附录：快速参考

- **节点类型**：`Root` `Sequence` `Step` `IfThenElse` `Branch` `Retry` `LoopUntil` `Action` `ref` `FunctionCall`
- **变量**：`Param.x`（读） / `NewParam.x[:type]`（写） / `returns` 键必须 `NewParam.<ASCII名>` / 变量名仅 ASCII
- **类型 token**：`str` `int` `float` `bool` `page_ref` `object`
- **主配置**：`autobranch.config.json`（llm / browser / run / max_concurrent_runs / experience_*）
- **代理配置**：`autobranch/plugins/browser/proxy.config.json`
- **内置插件**：`browser` `compute` `ssh` `file`；函数全名 `插件名.函数名`
- **端口**：后端 8001，前端 5174
- **数据库**：`data/autobranch.db`（自动创建）