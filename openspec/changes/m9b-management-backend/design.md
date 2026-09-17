## Context

AutoBranch 目前仅有引擎层（M0~M8）的 Python 代码与命令行工具；M9b 需要在此基础上新增一个可被 M9a 前端消费的后端服务。现状约束：

- 引擎（M7）作为 Python 库可直接 import，`engine.run()` 为同步入口，`get_exec_state()` 提供可查询执行状态（契约 §12.3）。
- M2 解析器提供 `BehaviorTreeParser.parse()`，返回 `ParseResult`（含 `CheckReport`），可直接复用做清晰度校验。
- M8 负责报告/截图产出，路径由执行状态携带，供后端持久化与提供。
- 项目规则强制：API 按 `api-conventions.md`（路由分层、错误码、异步执行 202、报告路径白名单）、数据库按 `database-rules.md`（SQLite + SQLAlchemy 2.0、表复数 snake_case、约束入库、文件落盘只存路径）。
- 动机见 proposal.md（Why），需求见 specs/management-backend/spec.md，此处只写"如何实现"。

## Goals / Non-Goals

**Goals:**
- 以 FastAPI 提供 REST 服务，路由只做 HTTP 编排，业务逻辑下沉到 service 层。
- 行为树文档与执行记录持久化到 SQLite（SQLAlchemy 2.0 ORM），报告/截图文件落盘 `data/reports/`。
- 执行以后台任务触发 M7 引擎（内嵌同进程），`run_id` 与引擎执行状态一一映射，轮询接口实时读取。
- 清晰度校验在保存与执行前两处复用一个 M2 校验入口。

**Non-Goals:**
- 不做实时推送（WebSocket/SSE）——按契约 §12.4 采用 1 秒轮询。
- 不做多进程/多机执行调度——单进程后台任务足够，执行状态存内存 + 执行记录持久化。
- 不实现前端 M9a 相关逻辑；不做身份认证/用户体系（本地单用户）。
- 引擎侧（M7/M8/M2）自身的能力不在本设计范围内，仅定义调用边界。

## Decisions

### D1: 应用结构：FastAPI + 分层目录（routers/schemas/services/models/db）
按 `api-conventions.md` §2.1，路由按资源组织（`routers/trees.py`、`routers/runs.py`、`routers/reports.py`），HTTP 编排与业务逻辑分离。
**备选**：路由内直接写业务（薄实现）。理由：被否——规则强制分层，且 mock 引擎独立测试时需要可注入的 service。

### D2: 引擎注入方式：以 service 层接口抽象 M7，测试时替换 mock
`EngineService` 封装 `engine.run()` 与 `get_exec_state()`，通过 FastAPI 依赖注入挂到路由；后台执行任务接收同一 service 引用。
**备选 A**：直接 import 全局单例引擎。被否——mock M7 的独立测试（spec §7）要求可替换。
**备选 B**：远程引擎进程。被否——契约 §12.3 明确内嵌同进程，共享内存、无序列化。

### D3: 执行触发：FastAPI BackgroundTasks 同步线程内跑阻塞式 `engine.run()`
`POST /api/trees/{id}/run` 立即校验（M2）→ 创建 `Run` 记录（status=pending，返回 run_id）→ 用 BackgroundTasks 起后台任务，在任务内调 `engine.run()` 并更新记录/状态。状态以 run_id 为键在内存中维护（engine 的 `get_exec_state()` + 后台任务结束时的最终状态快照）。
**备选 A**：`asyncio.create_task`。被否——`engine.run()` 是阻塞同步调用，会阻塞事件循环；BackgroundTasks 走线程池更安全。
**备选 B**：独立进程/subprocess。被否——违背内嵌契约。

### D4: 执行状态来源：内存 ExecState + Run 表持久化终态
轮询 `GET /runs/{run_id}/state`：进行中直接读引擎 `get_exec_state()`（同进程共享内存），结束读持久化的终态（`runs` 表 status + report_path + failure_reason）。
**备选**：全部状态写库实时落盘。被否——秒级轮询高频写库开销大，且终态持久化已满足"完成后可查询"需求（spec）。

### D5: 数据库模型：`trees` + `runs` 两表，报告元数据落库、文件落盘
- `trees`：id、name(unique)、content(Text)、created_at/updated_at（TimestampMixin）。
- `runs`：id、tree_id(FK→trees.id)、status(CheckConstraint: pending/running/success/failure)、failure_reason、report_path（相对路径）、created_at/updated_at。
- 报告/截图文件本体写 `data/reports/<run_id>/...`，库中只存相对路径，符合 `database-rules.md` §6。
**备选**：报告全文入 CL OB。被否——规则 §7 明确大字段落盘存路径。

### D6: 清晰度校验复用：单一校验函数，两处调用
service 内封装 `validate_document(content)` → 调 M2 `BehaviorTreeParser.parse()` 取 `CheckReport`；保存时与执行前都走它。失败抛 422（detail=CheckReport 错误清单），成功保存/触发。
**备选**：两处各写校验逻辑。被否——重复且易漂移，执行前校验语义必须与保存时一致。

### D7: 报告文件 HTTP 提供：路径白名单解析
`GET /api/reports/{path}`：resolve 后校验 `is_relative_to(REPORT_ROOT)`（见 `api-conventions.md` §7），再走 FileResponse。存在性由白名单校验后的路径判断，不存在返回 404。

### D8: 并发控制：同一文档进行中执行去重
`runs` 表加唯一部分索引或应用层检查（查该 tree 是否存在 status in (pending,running) 的 run），存在则 409。
**备选**：数据库唯一约束限制并发 run。被否——状态流转（pending→running→终态）会触发约束冲突，应用层检查更贴合状态机。

## Risks / Trade-offs

- [单进程后台任务在执行期间占用线程/资源，长时间运行可能堆积] → 同一文档去重（D8）+ 明确拒绝重复触发；单用户场景可接受。
- [进程重启丢失内存中的进行中执行状态] → 进行中的 run 记录持久化于 `runs` 表（status=running），重启后标记为 failure（failure_reason=interrupted），终态仍可查询。
- [BackgroundTasks 里跑阻塞引擎，异常若不捕获会中断任务] → 后台任务包裹 try/except，任何异常统一落 `failure_reason` 并置 status=failure。
- [报告文件增长无上限，磁盘占用风险] → 随 run 删除级联清理文件（ondelete CASCADE + 手动删目录），本版本不做配额/归档。
- [引擎 `run()` 与 `get_exec_state()` 的并发读取（轮询线程读、执行线程写）] → ExecState 以不可变/快照方式读取（取一次快照返回），避免半更新状态；必要时加锁。

## Migration Plan

- 全新模块，无既有数据迁移。开发期用 SQLAlchemy `create_all()` 建库（`database-rules.md` §5）；进入稳定期后引入 Alembic 基线。
- 回滚：删除 `autobranch/server/` 与数据库文件即可整体移除；API 无既有消费者，不破坏兼容。

## Open Questions

无——需求、契约与实现路径均已明确，无影响 spec/方案/任务划分的悬而未决项。