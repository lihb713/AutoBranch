## Why

AutoBranch 目前只有引擎层（M0~M8），用户必须以命令行方式书写行为树文档并本地执行，缺少一个供 M9a 前端消费的管理后端。M9b 作为系统阶段 6 的后端服务，负责行为树文档的持久化管理、清晰度校验、执行触发与状态查询、报告/截图提供，是引擎能力对外可用的必要入口；引擎以 Python 库内嵌同进程（契约 §12.3），无需进程间通信，实现简单且共享内存。

## What Changes

- 新增行为树管理系统后端服务（FastAPI + SQLite/SQLAlchemy），提供行为树文档 CRUD API（列表/创建/查看/修改/删除）。
- 新增清晰度校验能力：保存文档时复用 M2 解析器校验一次（返回错误清单供用户修正），执行前再校验一次确保可执行（契约 §12.5）。
- 新增执行触发与状态查询 API：`POST /api/trees/{id}/run` 异步触发内嵌引擎 M7 后台执行并立即返回 `run_id`；`GET /api/runs/{run_id}/state` 供前端每秒轮询执行状态（进度/当前节点/已完成报告/截图路径，契约 §12.4）。
- 新增执行报告与回溯报告接口（`GET /api/runs/{run_id}/report`、`GET /api/runs/{run_id}/trace`），以及报告/截图文件的 HTTP 提供接口（`GET /api/reports/{path}`，带路径白名单防目录穿越）。
- 新增持久化存储：行为树文档元数据与执行记录入库（`trees`、`runs` 等表），报告/截图文件本体落盘 `data/reports/`，库中只存相对路径。
- 引擎内嵌同进程：M7 `engine.run()` 与 `get_exec_state()` 直接以 Python 库形式调用，共享内存、无序列化传输。
- 新增执行状态数据契约 `ExecState`（run_id/progress/current_node/completed/finished）供轮询接口输出。

## Capabilities

### New Capabilities
- `management-backend`: 行为树管理系统后端服务，涵盖行为树文档 CRUD、清晰度校验、执行触发与状态轮询、报告/截图存储与 HTTP 提供、引擎内嵌同进程集成。

### Modified Capabilities
<!-- 无既有 capability 的需求变更，纯新增模块。 -->

## Impact

- **新增代码**：`autobranch/server/`（FastAPI 应用、routers、schemas、services、models、db）、执行任务管理（异步后台运行引擎）、报告文件服务。
- **API 面**：新增 `/api/trees`、`/api/trees/{id}/check`、`/api/trees/{id}/run`、`/api/runs/{run_id}/state|report|trace`、`/api/reports/{path}` 一组 REST 接口，供 M9a 前端消费。
- **依赖模块**：M2（解析器，清晰度校验）、M7（引擎，执行触发/状态查询）、M8（报告/截图机制），三者作为 Python 库同进程依赖。
- **被依赖模块**：M9a 前端 UI（消费全部 API）。
- **持久化**：新增 SQLite 数据库（文档库 + 执行记录）与报告/截图文件目录。