# AutoBranch 用户使用说明（完整版）

> 面向第一次使用 AutoBranch 的用户。假设你**从未用过**本工具：本文从"这是什么"开始，一步步教你安装、配置、写行为树、用前端编辑器、执行、看报告、写插件，以及所有支持的使用细节。遇到问题时查最后的「常见问题」。
>
> 快速上手（一页版）见 `README.md`；行为树语言契约与模块设计见 `docs/contract.md` / `docs/specs/`。

## 专题文档

本文保留安装、配置、界面、执行、报告、代理与排障等内容。以下主题已拆分为独立文档，建议按需阅读：

- [行为树指南](behavior-tree-guide.md)：基本概念、节点、变量黑板、入参出参、ref、FunctionCall、完整示例
- [插件开发指南](plugin-development-guide.md)：插件结构、save_to、自定义类型、配置与前端扩展
- [内置插件介绍](builtin-plugins.md)：browser / compute / transform / SSH / file / HTTP / vars 的函数与示例

---

## 目录

1. [AutoBranch 是什么](#1-autobranch-是什么)
2. [核心概念速成](#2-核心概念速成)
3. [安装与部署](#3-安装与部署)
4. [配置](#4-配置)
5. [前端界面导航](#5-前端界面导航)
6. [行为树指南](behavior-tree-guide.md)
7. [前端编辑器：可视化构建行为树](#7-前端编辑器可视化构建行为树)
8. [行为树指南：变量与黑板](behavior-tree-guide.md#6-变量与黑板)
9. [执行与报告](#9-执行与报告)
10. [内置插件介绍](builtin-plugins.md)
11. [插件开发指南](plugin-development-guide.md)
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
| 行为树文档 | 一份 YAML 文本，`tree/nodes/root` 三段式 | [行为树指南](behavior-tree-guide.md) |
| 节点 | 组合节点（流转）或叶子（Action/Condition/ref/FunctionCall/Define） | [行为树指南](behavior-tree-guide.md) |
| 变量 | `Param.x` 读、`NewParam.x[:类型]` 写（仅 Action 描述）、`returns` 裸名接收、`Define` 声明 | [变量与黑板](behavior-tree-guide.md#6-变量与黑板) |
| 入参/出参 | 文档级 `inputs`（外部传入）、`outputs`（对外返回） | [行为树指南](behavior-tree-guide.md) |
| 条件 | 单行自然语言（LLM）或谓词表达式（`all/any/not` + 单 bool 函数） | [条件指南](behavior-tree-guide.md#513-条件自然语言与谓词表达式) |
| 插件 | 能力集合（浏览器/计算/SSH/文件/HTTP/变量/数据变换/谓词/自定义），函数以 `插件名.函数名` 标识 | [内置插件](builtin-plugins.md) / [插件开发](plugin-development-guide.md) |
| 执行实例 | 一次执行 = 自包含实例（快照 + 入参 + 出参） | §9 |
| 报告 | 执行报告（节点结果+截图）/ 回溯报告（含 LLM 推理） | §9.5 |

**最重要的一条规则**：行为树文档中，**参数名与节点 id 只支持 ASCII 标识符**（`[A-Za-z_][A-Za-z0-9_]*`，不支持中文）。读取用 `Param.x`，写入声明 `NewParam.x[:类型]` **仅用于 Action 的描述**；`ref`/`FunctionCall` 的 `returns` 键为**接收名**（不接受 `NewParam.` 前缀）；`Define` 节点用于声明变量。违反会在保存/执行前被校验拒绝。接收名与类型默认由后端自动生成（`<节点id>_<返回参数名>`），用户只改名称，类型只读。

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
    "max_rounds": 20,
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
  "experience_retention": 5,
  "scheduler_tick_seconds": 10,
  "timezone": "Asia/Shanghai"
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
| `channel` | 用系统已安装的浏览器发行版通道（如 `chrome` / `msedge`），**无需下载** | 空 |
| `executable_path` | 指定浏览器可执行文件路径（优先于 `channel`） | 空 |

> **无法下载无头浏览器怎么办？** Playwright 默认用自带 Chromium（需 `playwright install chromium`）；网络受限时可改用本机浏览器：
> - `"channel": "chrome"`：使用已安装的 Google Chrome；`"channel": "msedge"`：使用 Edge；
> - 或 `"executable_path": "C:/Program Files/Google/Chrome/Application/chrome.exe"` 直接指定二进制。
> 二者配置后**无需下载** Playwright 浏览器；未配置则用自带浏览器（需先安装）。

**`run`（引擎运行）**

| 键 | 说明 | 默认 |
|---|---|---|
| `timeout` | 单叶子全局超时（秒；`null` 不检测） | 240 |
| `max_rounds` | 叶子 LLM 工具调用轮数上限 | 20 |
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
| `scheduler_tick_seconds` | M10 调度线程检查间隔（秒） | 10 |
| `timezone` | 项目时区（IANA 名称，影响时间戳与 cron 解释） | `Asia/Shanghai` |

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
| **行为树管理** | `/` | 行为树列表、导入/导出/新建、编辑/执行/删除 |
| **行为树执行列表** | `/runs` | 所有执行实例（进行中/历史），查看/重试/删除 |
| **插件管理** | `/plugins` | 查看/编辑/新增/删除插件 |

（编辑器页 `/editor`、执行详情页 `/runs/{id}` 通过点击进入，不占页签。）

---

## 6. 行为树文档语法

行为树的基本概念、节点类型、变量黑板、ref、FunctionCall、Define、ForEach 与完整示例，已整理到独立文档：

- **[行为树指南](behavior-tree-guide.md)**

## 7. 前端编辑器：可视化构建行为树

打开「行为树管理」→ 点「新建行为树」。系统会**立即创建草稿**（临时名 `未命名-<时间戳>`）并进入编辑器；首次点「保存」校验通过后改名为你填写的名称并转为**正式版**。

> **草稿/正式版**：同一棵树只有一份文档。对比正式版的任何修改都会让该树立即变为草稿；草稿**不能执行**，也不能被其他行为树 `ref` 引用，直到保存为正式版。列表显示「草稿/正式」徽标；删除按钮删除整棵树。

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

「行为树管理」页有「导入文档」（选择 `.yaml/.yml/.md/.txt` 文件，自动解析树名）与「新建行为树」；每行提供「导出」按钮，将当前完整文档下载为 `<行为树名>.yaml`（草稿/正式版均可导出）。也可直接在列表行点「编辑」进入已有树。

调度管理中新建调度时，选择目标行为树后会自动加载其 `inputs` 声明并渲染入参表单（str/int/float/bool/array/object/generics，array/object 填 JSON），无需手写 YAML；仅含 `page_ref` 等不可构造入参的树不会出现在目标下拉中。

---

## 8. 变量详解

变量、黑板、类型系统与作用域的完整说明，见：

- **[行为树指南：变量与黑板](behavior-tree-guide.md#6-变量与黑板)**

## 9. 执行与报告

### 9.1 触发执行

「行为树管理」列表每行对**正式版**显示「执行」按钮（草稿不显示）：

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
- **执行进度**：进度条 + 当前节点 + 已完成节点（成功/失败着色；**浏览器**操作/判断节点附**节点执行后**的页面截图——即点击/输入等操作的结果状态；**纯计算节点不截图**）。
- **执行报告 / 回溯报告** 切换查看。
- **黑板**：当前帧变量快照（路径/类型/值）。

### 9.5 报告内容

| 报告 | 内容 |
|---|---|
| **执行报告**（exec_report） | 每个节点的类型/描述/结果/失败原因/耗时/时间/URL；FunctionCall 打印函数名与实际 args/kwargs/returns；ForEach 打印变量/迭代次数/失败迭代数；**浏览器节点的执行后页面截图** |
| **回溯报告**（trace_report） | 执行报告的全部内容 + 明显的 LLM 推理区块（输入/推理过程/工具调用序列/决策/终止条件）；纯 FunctionCall 树无 LLM 推理时与执行报告内容一致（除标题/截图差异） |

看"为什么这么走"，看回溯报告；看"结果如何"，看执行报告。

### 9.6 重试 / 删除

- **重试**：复制该实例的快照+入参新建执行（跑的是**当时的内容**，不是树的最新版本）。
- **删除**：删除实例并清理其报告目录；删除行为树保留历史。

---

## 10. 内置插件与函数详解

浏览器、计算、数据变换、SSH、文件、HTTP、变量、谓词插件的函数清单与示例，见：

- **[内置插件介绍](builtin-plugins.md)**

## 11. 自定义插件开发

插件结构、函数注册、save_to、自定义类型与调试方式，见：

- **[插件开发指南](plugin-development-guide.md)**

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
| 保存报 `syntax.invalid_return_name` | `returns` 键要用裸 ASCII 名（如 `loginOk`），不能带 `NewParam.`/点号/中文 |
| 保存报 `syntax.invalid_name` | 变量名用了中文/非 ASCII；变量名只能是 ASCII 标识符 |
| 排队中一直不执行 | 并发上限（`max_concurrent_runs`）满了，等前面的结束自动调度 |
| 端口 5174 / 8001 被占 | AutoBranch 固定用这两个；检查是否被其他程序占用并释放 |
| 浏览器插件报"浏览器未装配" | 叶子要先 `use_capability("browser")` 或行为树用到浏览器能力 |
| `ref` 找不到目标文档 | 确认被调文档名存在且 `target` 拼写正确 |

---

## 15. 附录：快速参考

- **节点类型**：`Root` `Sequence` `Step` `IfThenElse` `Branch` `Retry` `LoopUntil` `ForEach` `Action` `ref` `FunctionCall` `Define`
- **变量**：`Param.x`（读） / `NewParam.x[:type]`（写，仅 Action 描述） / `returns` 键为裸 ASCII 名 / `Define` 声明变量 / 变量名仅 ASCII
- **类型 token**：核心 `str` `int` `float` `bool` `array` `object` `generics` `page_ref`，以及插件注册的自定义类型（如 `ssh_session`、`page_object`）
- **主配置**：`autobranch.config.json`（llm / browser / run / max_concurrent_runs / scheduler_tick_seconds / timezone / experience_*）
- **代理配置**：`autobranch/plugins/browser/proxy.config.json`
- **内置插件**：`browser` `compute` `ssh` `file` `http` `vars` `transform` `predicate`；函数全名 `插件名.函数名`
- **端口**：后端 8001，前端 5174
- **数据库**：`data/autobranch.db`（自动创建）