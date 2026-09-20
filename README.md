# AutoBranch

**AutoBranch** 是一个**自然语言驱动的 LLM 行为树自动化工具**。用户用 YAML/Dict 编写**行为树文档**，描述"做什么、怎么判断、如何循环"，AutoBranch 通过 LLM Agent 逐叶执行，并把浏览器 / 计算 / SSH / 文件等能力以**插件**形式注入，最终产出结构化执行报告与截图。

它**不限于 Web 自动化**：除了浏览器，还内置计算、SSH、文件等能力，且支持用户编写自定义插件——因此从最初的"网页自动化"演变为通用的自动化执行平台。

## 核心特性

- **行为树文档驱动**：`tree / nodes / root` 三段式 YAML，支持 Sequence / Selector / Repeat / LoopUntil / Retry / Step / Branch / ref / **FunctionCall** 等节点。
- **LLM Agent 叶子执行**：Action / Condition 由 LLM 依据语义图决策，调用插件函数并**落笔写变量**（引擎回收返回值，按类型 coerce）。
- **确定性 FunctionCall 节点**：行为树可直接调用插件函数（`compute.add` 等），不经 LLM，可精确写变量 / 多返回值。
- **插件框架**：预置浏览器 / 计算 / SSH / 文件插件 + 用户自定义插件（DB 源码，仅标准库）；函数以**全名 `插件名.函数名`** 标识，跨插件可同名；两级能力选择（`use_capability`）+ 懒装配。
- **语义图 + 引用定位**：浏览器插件自包含驱动与语义图生成，元素以 ref（`[N]`）+ 真实 DOM 索引路径精确定位。
- **管理后端 + 前端**：行为树 CRUD / 清晰度校验 / 执行触发与状态轮询 / 报告与截图；前端提供画布式行为树编辑器、插件管理页、执行报告页。
- **执行实例化**：每次执行保存**行为树快照 + 入参**（触发时刻冻结，执行/重试不随实时树变化）；支持根级入参注入与出参返回、执行列表页（进行中/历史回看）、FIFO 队列调度（全局并发上限可配置）、按快照重试；含不可序列化入参（如 page_ref）的树仅支持 ref 调用。
- **经验回灌**：整树成功的历史经验（节点级成功调用路径，去 ref 化）存入经验库，同条件（同行为树快照 + 同入参 + 同节点）重跑时以"参考而非指令"注入叶子提示词（以当前语义图为准、与当前状态不符时忽略），降低 LLM 随机性导致的同树重跑失败；按匹配组自动老化。

## 目录结构

```
autobranch/
  config.py                引擎统一配置（LLM/浏览器等）
  llm/                     M0 LLM 客户端（OpenAI 兼容，重试/预算/流式）
  parser/                  M1 行为树解析 + 清晰度校验
  schema/                  M2 变量空间 / 类型契约（str/int/float/bool/page_ref/object）
  plugin_system/           M3 插件框架（注册表/懒装配/能力选择/分发/报告）
  leaf_agent/              M4 叶子 Agent（Action/Condition 执行）
  orchestrator/            M5 编排器（遍历/FunctionCall/超时/会话）
  plugins/                 M7 插件集（browser/compute/ssh/file + common）
  reporting/               报告 / 截图 / 回溯
  server/                  M8 管理后端（FastAPI：trees/runs/reports/plugins/functions）
  frontend/                M9 前端（React + Vite：编辑器/插件管理/报告）
tests/                     后端测试（含真实浏览器集成）
docs/
  contract.md              行为树语言契约与模块说明
  specs/                   M0–M9 模块规格
  tmp/                     设计草稿
openspec/                  需求规格（spec-driven，含归档变更）
scripts/                   一次性迁移脚本（函数全名迁移 / runs 执行实例快照迁移）
```

## 安装

### 后端（Python）

要求：Python 3.11、conda/miniforge（可选）、Git。

```bash
# 1. 创建独立 conda 环境（推荐，避免污染 base）
conda create -n autobranch python=3.11 -y
conda activate autobranch

# 2. 安装依赖 + 以可编辑模式安装本包
pip install -e .
```

> 若已有 conda 环境，直接 `conda activate autobranch` 后 `pip install -e .` 即可。

### 前端（可选，管理界面）

要求：Node.js 18+。

```bash
cd autobranch/frontend
npm install
```

### 浏览器插件依赖

浏览器插件基于 Playwright，需安装 Chromium：

```bash
conda run -n autobranch python -m playwright install chromium
```

### 数据库

- **无需手动初始化**：AutoBranch 使用 **SQLite 单文件库**。后端（`uvicorn ... autobranch.server.main:app`）首次启动时自动创建数据库文件并建表（`configure_database` → `create_all`），安装后直接启动即可。
- 默认数据库文件位于 `data/autobranch.db`（`data/` 目录会自动创建）。
- **既有库升级**：`runs` 表升级为"执行实例"（新增快照/入参/出参列、`tree_id` 改 SET NULL）时，运行 `conda run -n autobranch python -m scripts.migrate_runs_snapshot`（幂等，可从任意旧版本升级）。

## 配置

项目读取根目录 `autobranch.config.json`（示例见下方；该文件已加入 `.gitignore`，请勿提交含密钥的配置）。支持的环境变量：

| 变量 | 说明 |
|---|---|
| `AUTOBRANCH_LLM_API_KEY` | LLM API 密钥（优先于配置文件） |
| `AUTOBRANCH_DB_PATH` | SQLite 数据库路径（默认 `data/autobranch.db`） |
| `AUTOBRANCH_REPORT_DIR` | 报告/截图持久化目录（默认 `data/reports`） |

> 配置项：
> - `max_concurrent_runs`（顶层，默认 3）：服务端**执行并发上限**（同时最多运行 N 个执行实例，超出的进入 FIFO 排队）。
> - `experience_feedback`（顶层，默认 true）：**经验回灌开关**（关闭时不采集也不注入）。
> - `experience_retention`（顶层，默认 5）：**经验老化**——每个匹配组（同树同入参同节点）只保留最近 N 条经验。

> **数据库连接说明**：`autobranch.config.json` 中**不需要**（也没有）数据库连接项——SQLite 为单文件库，路径由 `AUTOBRANCH_DB_PATH` 环境变量或默认值 `data/autobranch.db` 决定，无连接串/账号配置；后端启动时自动初始化建表。如需更换数据库位置，设置环境变量即可，无需改动配置文件或代码。

```json
{
  "llm": {
    "base_url": "https://opencode.ai/zen/go/v1",
    "api_key": "sk-...",
    "model": "deepseek-v4-flash",
    "timeout": 60
  },
  "browser": {
    "headless": true,
    "timeout_ms": 30000
  },
  "max_concurrent_runs": 3,
  "experience_feedback": true,
  "experience_retention": 5
}
```

## 使用

### 启动

```bash
# 后端（8001，Swagger: /docs）
conda run -n autobranch python -m uvicorn autobranch.server.main:app --host 127.0.0.1 --port 8001

# 前端（5174）
cd autobranch/frontend && npm run dev
```

Windows 下可用一键脚本：`powershell -ExecutionPolicy Bypass -File .\dev-restart.ps1`（固定端口 8001 / 5174）。

### 编写并执行行为树

行为树是 YAML 文档，三段式：`tree`（文档名）、`nodes`（节点）、`root`（根节点）。示例（登录并提取表格求和）：

```yaml
tree: 表格求和演示
nodes:
  n1:
    type: Root
    body: n2
  n2:
    type: Sequence
    actions: [登录步骤, 提取苹果, 提取香蕉, 求和]
  登录步骤:
    type: Step
    action: 登录动作
    expect: 页面出现"销售数据表"
  登录动作:
    type: Action
    description: 打开测试页，输入 admin/secret，点击登录
  提取苹果:
    type: Action
    description: 用 extract 提取"苹果"行金额，写入变量 appleAmount NewParam.appleAmount:int
  求和:
    type: FunctionCall
    function: compute.add
    args: [Param.appleAmount, Param.bananaAmount]
    returns:
      NewParam.fruitTotal: int
root: n1
```

- 通过前端「行为树管理」创建 / 保存（保存时做清晰度校验，FunctionCall 会校验函数存在性与参数对齐）。
- 点击「执行」→ 若声明了入参则弹框填参（含不可序列化入参的树不显示「执行」按钮）→ 后台异步运行 → 前端轮询状态 → 展示执行报告与出参。
- 「行为树执行列表」页可查看全部执行实例（进行中/历史）、轮询进度、重试（按当时快照+入参）、查看快照、删除记录。
- 也可直接调用 API：`POST /api/trees/{id}/run`（可选 body `{"inputs": {...}}`）。

### 插件管理

- 预置插件：浏览器 / 计算 / SSH / 文件（启动自动加载）。
- 自定义插件：前端「插件管理」页编写 Python 源码（仅标准库），保存即校验并重载；删除时提示关联行为树并置空引用。
- 函数清单：`GET /api/functions` 返回全部函数（全名 + 结构化定义），供编辑器函数选择器使用。

## 概要设计

核心思想：**引擎核心不感知具体能力，能力全部插件化**。行为树叶子（Action/Condition）由 LLM Agent 驱动，能力经插件框架分发；确定性运算用 FunctionCall 节点。

```
┌─────────────────────────────────────────────────────────────┐
│  行为树文档 (YAML)                                            │
│  tree / nodes / root + inputs/outputs/config                 │
└───────────────┬─────────────────────────────────────────────┘
                │ 解析（M1）→ 校验（清晰度）
                ▼
┌─────────────────────────────────────────────────────────────┐
│  编排器 (M5)                                                  │
│  遍历：Sequence/Selector/Repeat/LoopUntil/Retry/Branch        │
│  ├─ Action/Condition → 叶子 Agent (M4)                       │
│  │     LLM + 语义图 → 插件函数调用 → 落笔变量                 │
│  └─ FunctionCall → 确定性调用插件函数（不经 LLM）             │
└───────────────┬─────────────────────────────────────────────┘
                │ 统一分发（M3 插件框架）
                ▼
┌─────────────────────────────────────────────────────────────┐
│  插件层 (M7)                                                  │
│  browser（驱动/语义图/ref 定位） compute ssh file + 自定义     │
└─────────────────────────────────────────────────────────────┘
                │ 报告（M6）
                ▼
        执行报告 + 截图 + 回溯
```

### 模块划分（M0–M9）

| 模块 | 职责 |
|---|---|
| M0 LLM | OpenAI 兼容客户端：多轮工具调用 / 重试 / token 预算 / 流式 |
| M1 解析 | 行为树解析 + 清晰度校验（结构/引用/循环/变量契约/FunctionCall 校验） |
| M2 变量空间 | 帧命名空间 / 严格作用域 / 类型契约（含泛型 `object`） |
| M3 插件框架 | 注册表（全名）/ 懒装配 / `use_capability` 两级能力选择 / 统一分发 / 报告接口 |
| M4 叶子 Agent | Action / Condition 的 LLM agent 式执行 + 变量落笔 |
| M5 编排器 | 遍历语义 / 超时 / 会话初始化 / FunctionCall 确定性执行 |
| M6 报告 | 执行报告 / 截图 / 回溯 / 可查询状态 |
| M7 插件集 | browser / compute / ssh / file + 自定义插件 |
| M8 管理后端 | FastAPI：trees / runs（执行实例：快照/入参/出参/列表/重试/队列）/ reports / plugins / functions / types |
| M9 前端 | React + Vite：行为树编辑器 / 插件管理 / 执行报告 / 执行列表 |

## 测试

```bash
# 后端（非集成，快速）
conda run -n autobranch python -m pytest -m "not integration"

# 后端全量（含真实浏览器集成，需 Chromium）
conda run -n autobranch python -m pytest

# 静态检查
conda run -n autobranch python -m ruff check autobranch tests scripts

# 前端
cd autobranch/frontend
npm run typecheck && npm run lint && npm test
npm run test:e2e          # 端到端（需前后端已启动，部分用例需 LLM API）
```

## 文档

- `docs/contract.md`：行为树语言契约（节点/类型/校验/API 约定）与模块说明。
- `docs/specs/`：M0–M9 各模块规格。
- `openspec/specs/`：需求规格（spec-driven）；`openspec/changes/archive/` 为已归档变更。
- `AGENTS.md`：面向 AI 助手的开发规范（测试/文档同步要求）。