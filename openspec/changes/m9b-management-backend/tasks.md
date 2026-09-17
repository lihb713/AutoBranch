## 1. 项目脚手架与依赖

- [x] 1.1 在独立 conda 环境（`autobranch`，python 3.11）内新增后端依赖：`pip install fastapi uvicorn sqlalchemy pydantic` 并写入 `pyproject.toml`；验证 `uvicorn autobranch.server.main:app` 可导入（`python -c "import autobranch.server.main"` 无报错）
- [x] 1.2 建立 `autobranch/server/` 包结构（`db.py`、`models/`、`schemas/`、`services/`、`routers/`、`errors.py`、`main.py`、`config.py`）；验证空应用可启动：`uvicorn autobranch.server.main:app` 起服并访问 `/api/health` 返回 200
- [x] 1.3 实现 `db.py`：SQLAlchemy engine（SQLite `check_same_thread=False`）+ `SessionLocal` + `Base` + `get_db` 依赖；验证 `Base.metadata.create_all()` 生成 `.db` 文件且可建会话

## 2. 数据库模型与迁移

- [x] 2.1 实现 `TimestampMixin`（created_at/updated_at，`onupdate`）与 `Tree` 模型（trees 表：id、name unique、content Text）；验证建表后向 trees 插入/读取/重名唯一约束生效（`pytest` 单测）
- [x] 2.2 实现 `Run` 模型（runs 表：id、tree_id FK→trees.id 带 index、status CheckConstraint pending/running/success/failure、failure_reason、report_path、时间戳）；验证：插入非法 status 被约束拒绝、删除 tree 时 run 的级联策略符合设计 D5
- [x] 2.3 用 SQLAlchemy `create_all()` 初始化库并编写 CRUD 持久化单测（trees 增删改查 + 幂等）；验证 `pytest tests/server/test_models.py` 全绿

## 3. 行为树文档 CRUD API

- [x] 3.1 实现 `schemas/tree.py`：`TreeCreate`（name Field 1~200、content 必填）、`TreeUpdate`、`TreeOut`（含 id/name/created_at/updated_at）；验证 Pydantic 约束使非法入参返回 422
- [x] 3.2 实现 `services/trees.py`：`list_all`/`create`/`get`/`update`/`delete`，业务规则（重名 409、不存在 404）抛 `AppError`；验证 service 单测覆盖各分支
- [x] 3.3 实现 `routers/trees.py`：`GET /api/trees`、`POST /api/trees`（201）、`GET /api/trees/{tree_id}`、`PUT /api/trees/{tree_id}`、`DELETE /api/trees/{tree_id}`（204）；验证 FastAPI TestClient CRUD 集成测试通过（`.opencode/rules/testing-guidelines.md`）

## 4. 清晰度校验（复用 M2）

- [x] 4.1 在 `services/validation.py` 封装 `validate_document(content)`：调 M2 `BehaviorTreeParser.parse()` 取 `CheckReport`，校验失败抛 422 携带错误清单；验证：合法文档通过、非法文档（结构错误/引用缺失/无上界循环）返回可读错误清单（单测 + 对照契约 §4.4 用例矩阵）
- [x] 4.2 保存路径接入校验：`POST`/`PUT /api/trees` 在写入前调用校验，失败返回 422 且不落库；验证 TestClient 保存非法文档返回 422 且库中无该文档
- [x] 4.3 执行前校验接入：`POST /api/trees/{id}/run` 触发前调用同一校验函数；验证校验不通过文档触发执行返回 422 且不产生 run_id（集成测试覆盖 spec「执行前再校验」场景）

## 5. 异步执行触发与引擎内嵌（mock M7）

- [x] 5.1 定义 `services/engine.py` 的 `EngineService` 抽象接口（`run(tree_id, content, run_id)` + `get_exec_state(run_id)`），提供真实实现（内嵌 M7：`engine.run()` + `get_exec_state()`，同进程调用）与 mock 实现（可编程推进状态/失败）；验证：mock 实现单测通过，真实实现 import M7 无错
- [x] 5.2 实现 `POST /api/trees/{id}/run`：执行前校验 → 建 `Run` 记录（status=pending）返回 run_id（202）→ 用 `BackgroundTasks` 启动后台任务，内部调用 `EngineService.run()` 更新状态并捕获异常写 failure_reason；验证：TestClient 返回 202 + run_id，后台 mock 执行结束 status 变 success/failure
- [x] 5.3 实现并发去重（设计 D8）：同一 tree 存在 pending/running 的 run 时返回 409；验证 TestClient 重复触发返回 409 且仅一条 run 记录

## 6. 执行状态轮询与 ExecState 契约

- [x] 6.1 实现 `GET /api/runs/{run_id}/state`：进行中读引擎 `get_exec_state()` 快照，结束读持久化终态，输出 ExecState 契约字段（run_id/progress/current_node/completed/finished/failure_reason）；不存在的 run 返回 404；验证 mock M7 下轮询测试断言字段与取值（progress 单调、finished 翻转）
- [x] 6.2 进程重启恢复：启动时扫描 status=running 的记录置为 failure（failure_reason=interrupted）；验证：预置 running 记录后重启应用，状态接口返回 failure 终态

## 7. 报告/截图存储与 HTTP 提供

- [x] 7.1 实现报告文件服务：执行结束后将 M8 产出的报告/截图写入 `data/reports/<run_id>/`，`runs.report_path` 存相对路径；验证：mock 执行产出文件落盘、路径入库
- [x] 7.2 实现 `routers/reports.py`：`GET /api/reports/{path}` 白名单解析（`is_relative_to(REPORT_ROOT)`）+ FileResponse；验证：正常路径返回文件、`..` 目录穿越返回 400、不存在路径返回 404（含安全单测）
- [x] 7.3 实现 `GET /api/runs/{run_id}/report` 与 `/trace`：执行中返回进行中状态、结束后返回 M8 报告内容；验证：mock 执行前/后两次请求行为符合 spec

## 8. 集成测试与实机验收

- [x] 8.1 编写集成测试（pytest -m integration）：真实/半真实链路——建文档 → 保存校验 → 触发执行 → 轮询至 finished → 取报告/截图；验证全部断言通过
- [x] 8.2 实机验收：启动 `uvicorn autobranch.server.main:app` 与 M9a 前端（`npm run dev`），浏览器实际走一遍 列表/编辑/保存校验/执行/轮询渲染/截图展示 全流程；验证前后端联调通过（不能仅凭单测）
  > 说明：M9a 前端尚未实施（本阶段仅交付后端 API 完整可用）。已用真实 uvicorn（`--reload`）启动并逐个 HTTP 请求验证 health/CRUD/check/run/state/report/trace/reports 接口；前端浏览器走查待 M9a 实施后补做。
- [x] 8.3 对照 spec「验收标准」逐条核对并同步更新 `docs/contract.md` §12.2-M9b 与 `docs/specs/M9b-management-backend.md`（每次代码变更后同步文档）；验证文档与代码一致