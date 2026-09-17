> **模块重编号**：原 **M9b 管理后端** 重编号为 **M8**。新增插件管理 API 与 plugin 表。

# M9b · 行为树管理系统后端 Spec

> 依据契约 `docs/contract.md` §12.2-M9b（功能）、§12.3（引擎内嵌形态）、§12.4（前端执行报告轮询）、§12.5（清晰度校验位置）、§4.4（清晰度校验）。
>
> **实现状态：全部功能已实现并通过测试 ✅（openops change `m9b-management-backend`）**

## 1. 概述

AutoBranch 的后端服务：行为树文档 CRUD API、清晰度校验（复用 M2）、执行触发与状态查询（内嵌引擎 M7）、报告/截图存储与提供。**引擎作为 Python 库内嵌于同一进程（§12.3），无进程间通信。依赖 M2 + M7 + M8。**

实现位置：`autobranch/server/`（FastAPI 应用、routers、schemas、services、models、db）。

## 2. 功能范围

| 功能 | 说明 | 契约依据 | 状态 |
|---|---|---|---|
| 行为树文档 CRUD API | 存储/管理行为树文档 | §12.2-M9b | ✅ `routers/trees.py` + `services/trees.py` |
| 清晰度校验 | 保存时校验（复用 M2 解析器），执行前再校验；**注入共享插件注册表**校验 FunctionCall 的 `function` 存在性与 `args` 参数对齐（函数不存在 / 参数不匹配 → 保存 422 拒绝） | §12.5/§4.4 | ✅ `services/validation.py`（单一入口，两处复用） |
| 执行触发 | 调引擎.run（M7，异步后台执行） | §12.4 | ✅ `routers/trees.py` + `services/runs.py` |
| 执行状态查询 API | 返回进度/当前节点/已完成报告/截图（供前端轮询） | §12.4 | ✅ `GET /api/runs/{id}/state` |
| 截图/报告存储与提供 | 持久化报告与截图，HTTP 提供 | §12.4 | ✅ `services/reports.py` + `routers/reports.py` |
| 引擎内嵌 | 与 M7 同一进程，共享内存 | §12.3 | ✅ `services/engine.py`（`EmbeddedEngineService`） |

## 3. 数据依赖

### 3.1 输入
- **行为树文档**（来自 M9a）：存储/校验/执行
- **引擎能力**（来自 M7）：`engine.run()`、执行状态查询
- **解析器**（来自 M2）：保存时校验

### 3.2 输出
- **API 响应**：CRUD 结果、校验报告、执行状态、报告/截图
- **持久化数据**：文档库（SQLite `data/autobranch.db`）、报告文件（`data/reports/`）

## 4. 单元间依赖

- **依赖**：
  - M2（行为树解析器）— 清晰度校验
  - M7（编排器/引擎）— 执行触发、状态查询
  - M8（报告机制）— 报告/截图提供
- **被依赖**：
  - M9a（前端 UI）— 全部 API 消费

## 5. 接口契约（全部已实现）

### 5.1 行为树管理 API

```
GET    /api/trees              # 列表（200，元数据数组）
POST   /api/trees              # 创建（201，元数据；保存时校验 422 拒绝，含树名=文档名强制）
GET    /api/trees/by-name/{name}  # 按文档名查（200，含 content；ref 展开/参数加载/文档库）
GET    /api/trees/{id}         # 查看（200，含 content）
PUT    /api/trees/{id}         # 修改（200；至少提交 name/content 之一，校验 422 拒绝，含树名=文档名强制）
DELETE /api/trees/{id}         # 删除（204；级联删除执行记录并清理报告文件）
POST   /api/trees/{id}/check   # 清晰度校验（200，CheckReport：ok + issues 错误清单，不落库）
```

- 错误：资源不存在 404、重名 409、参数/文档校验失败 422（detail 为 CheckReport 错误清单）。
- 422 detail 结构：`[{"code", "message", "rule", "loc"}, ...]`（可读、可定位，对齐 §4.4 八类）。

### 5.2 执行 API

```
POST   /api/trees/{id}/run            # 触发执行（异步 202 → {"run_id": n}）
GET    /api/runs/{run_id}/state       # 轮询执行状态（ExecStateOut）
GET    /api/runs/{run_id}/report      # 执行报告（进行中 200 {"status":"running"}，结束 text/markdown）
GET    /api/runs/{run_id}/trace       # 回溯报告（同上）
GET    /api/reports/{path}            # 截图/报告文件（白名单防目录穿越）
```

- 执行前校验（§12.5）：触发 `run` 前复用 M2 校验，失败 422 且不产生 run_id。以树名（name）作为 doc_id 校验（`validate_document(tree.content, tree.name)`；文档 `tree` 键须 = 树名），帧 doc_id 取解析出的树名。
- 并发去重：同一 tree 存在 pending/running 的 run 时返回 409。
- `GET /api/reports/{path}`：`resolve()` 做 `is_relative_to(REPORT_ROOT)` 白名单，越界 400、不存在 404；`.md`→`text/markdown`、`.png`→`image/png`。

### 5.3 执行流程（§12.4）

```
① 前端 POST /run → 建 Run(pending) → 202 run_id → BackgroundTasks 后台执行
② 后台任务：置 running → 内嵌 M7 引擎.run（同进程）→ 落终态（status/failure_reason/report_path）
③ 前端每 1 秒轮询 GET /state（进行中读引擎内存快照，结束读终态）
④ 执行完毕 → GET /report + /trace 展示完整报告
```

- **进程重启恢复**：应用启动时扫描 running/pending 记录置 failure（`failure_reason="interrupted"`），终态仍可查询。
- **执行配置**：`AutoBranchConfig.load()` 统一加载（§6.3），经 `to_run_config()` 构建 `RunConfig`（report_dir 指向 `data/reports/` 绝对路径）；真实引擎按 e2e 装配注入 M5 `EngineFunctions`（MockFiller 语义图）+ 可选 M0 `LLMConfig`（api_key 可直接写入配置文件 `llm.api_key`，或经 `AUTOBRANCH_LLM_API_KEY` 注入，环境变量优先）。
- **文档库（跨文档引用）**：`services/doclib.py::DbResolver` 按文档名从 DB 加载 `Tree.content` → `DocumentSource`，实现 M2 `RefResolver`；校验/执行装配经它解析 `ref`（替换旧空 `MappingResolver`，保证生产环境跨文档引用可解析）。

### 5.4 数据契约

```python
# 输出（M8 ExecState 对齐 §12.4，附 failure_reason）
@dataclass
class ExecStateOut:
    run_id: str
    progress: float          # 0.0~1.0
    current_node: NodeInfo | None
    completed: list[NodeReportOut]
    finished: bool
    failure_reason: str | None
    variables: list[dict]    # blackboard 变量快照 [{path, type, value}]（§5.3 扩展，供前端变量黑板）
```

- `completed` 元素字段：node_type/node_desc/result/timestamp/action_call/condition_result/page_url/screenshot_path（LLM 推理数据在 trace 报告中提供，不在轮询负载内）。
- **数据模型**（`models/`，database-rules §2/§3）：
  - `trees`：id、name(unique)、content(Text)、created_at/updated_at
  - `runs`：id、tree_id(FK→trees.id ON DELETE CASCADE)、status(CheckConstraint pending/running/success/failure)、failure_reason、report_path(相对路径)、created_at/updated_at
  - SQLite 开启 `PRAGMA foreign_keys=ON` 使级联生效；报告/截图文件落盘 `data/reports/<run_id>/`，库中只存相对路径（database-rules §6）。

## 6. 验收标准（全部达成 ✅）

- [x] 行为树文档 CRUD 完整可用（列表/创建/查看/修改/删除）
- [x] 保存时校验：非法文档返回清晰校验报告，执行前再校验
- [x] 执行触发异步运行，返回 run_id
- [x] 执行状态轮询接口正确：进度/当前节点/已完成报告实时更新
- [x] 报告/截图可存储并可经 HTTP 提供
- [x] 引擎内嵌：同一进程调用 M7，无序列化传输
- [x] mock M7 下可独立测试 API 与文档管理

## 7. 测试策略（全部已实施 ✅）

- **mock M7 执行测试**：`tests/server/test_runs_api.py`（触发/轮询/并发/重启恢复）+ `test_engine_service.py`（mock 可编程推进）
- **CRUD 测试**：`tests/server/test_trees_api.py`（增删改查 + 持久化）+ `test_models.py`
- **校验测试**：`tests/server/test_validation.py`（复用 M2，§4.4 用例矩阵）
- **报告服务测试**：`tests/server/test_reports_api.py`（存储/HTTP 提供/路径穿越防护）
- **集成测试**（`pytest.mark.integration`）：`tests/server/test_integration.py`（内嵌真实引擎 + mock 浏览器/叶子，端到端）
- **独立性**：mock 引擎（M7）后可独立验收，不依赖 M9a ✅
- 测试统计：`tests/server/` 共 78 用例；全库 `pytest` 724 passed / 3 skipped（无回归）。
- **实机验收**：`uvicorn autobranch.server.main:app --reload` 启动，HTTP 请求验证 health/CRUD/check/run/state/report/trace/reports 全部可用。

## 8. 运行方式

```bash
conda run -n autobranch --no-capture-output python -m uvicorn autobranch.server.main:app --reload
# 可选环境变量：AUTOBRANCH_DB_PATH（默认 data/autobranch.db）、AUTOBRANCH_REPORT_DIR（默认 data/reports）
# 引擎真实执行需配置 api_key：AUTOBRANCH_LLM_API_KEY=sk-...（契约 §6.3）
```


## 8. 插件管理 API 与 plugin 表（能力插件化新增，已实现）

### 8.1 plugin 表

`plugins` 表字段：`name`（唯一，≤128，小写字母/数字/`_`/`-`）、`kind`（`builtin` | `custom`）、`description`、`functions`（JSON **函数全名**清单，如 `compute.add`）、`source`（仅 `custom` 存储；`builtin` 恒 NULL——源码在文件系统）、`created_at` / `updated_at`（UTC）。启动扫描 `plugins/` 初始化 / 刷新 `builtin` 记录（只读）；自定义插件名不得与预置同名。

### 8.2 插件 API

```
GET    /api/plugins                列表（含 kind，预置/自定义徽标；functions 为全名清单）
GET    /api/plugins/{name}         详情（builtin 返回文件源码供只读查看）
POST   /api/plugins                新增（校验：语法+仅标准库+可加载 → 通过才落库+重载）
PUT    /api/plugins/{name}         更新（自定义；重载成功才落库）
DELETE /api/plugins/{name}         删除（扫描引用其函数的行为树，FunctionCall 引用置空并持久化，返回受影响树名）
POST   /api/plugins/check          校验（返回行号/列号/类型/约束 错误明细）
GET    /api/plugins/{name}/references  引用该插件函数的行为树名列表
GET    /api/functions              函数清单（跨插件聚合：full_name/plugin/name/description/returns/parameters，编辑器选择器用）
```

### 8.3 自定义插件加载

源码存 DB，`compile + exec`（注入 `PluginBase` / `engine_function` / `FunctionResult`）加载；仅用 Python 标准库（不 import 其他插件 / `common` / 三方库）；直接使用注入的名字（不 import `autobranch`）。
