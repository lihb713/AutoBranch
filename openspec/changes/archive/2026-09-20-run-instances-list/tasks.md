# run-instances-list 任务

## 1. 数据模型与迁移

- [x] 1.1 `Run` 模型新增 `content_snapshot`/`tree_name_snapshot`/`tree_content_hash`(index)/`inputs`(JSON)/`outputs`(JSON) 列，`tree_id` 改 `nullable=True` + `ondelete="SET NULL"`；新增模型单测断言列存在、类型与默认行为
- [x] 1.2 编写 `scripts/migrate_runs_snapshot.py`（幂等：新列 `ALTER TABLE ADD COLUMN` + `tree_id` 约束走 SQLite 表重建，`PRAGMA foreign_keys=OFF`）；用旧结构临时库跑迁移，验证数据保留、新列可写、删树后 run.tree_id 置空

## 2. 执行结构指纹与引擎入参/出参

- [x] 2.1 实现 `compute_tree_content_hash(content)`（解析→规范节点图→sha256；剔除树名/节点名/入参/出参、保留列表顺序、`sort_keys` 规范化）；单测覆盖：改名/键序/注释不影响哈希、改节点内容/槽位/执行配置改变哈希
- [x] 2.2 `Engine.run` 支持 `run_inputs`（enter_frame 后按声明类型 coerce 写根帧 `this/<名>`）；`RunResult` 新增 `outputs`（遍历后按 `decl_outputs` 读根帧）；单测覆盖入参注入（叶子 Param 可读）与出参返回
- [x] 2.3 出参 JSON 安全序列化工具（标量原样 / PageRef→{page_id,url} / 对象→str(value) 截断）；单测覆盖各类值

## 3. 队列调度

- [x] 3.1 配置 `max_concurrent_runs`（默认 3，`autobranch.config.json` 可覆盖）；单测断言默认值与覆盖生效
- [x] 3.2 `RunService` 重构：懒建 `ThreadPoolExecutor(max_workers=N)` + `_drain()`（进程内锁，先置 running 占位再 submit，完成路径末尾再 drain，FIFO 按 created_at/id）；单测覆盖并发上限、FIFO 顺序、完成自动调度
- [x] 3.3 移除 D8 同树并发 409 去重，改为全局上限排队；API 集成测试验证同树/异树并发触发不被拒、超上限进排队

## 4. 后端 API

- [x] 4.1 `POST /trees/{id}/run` 接收可选 `inputs`（按声明类型校验）并冻结快照+入参；含不可构造入参（page_ref/object）返回 422 且明确提示；API 测试覆盖
- [x] 4.2 `GET /api/runs` 列表接口（快照树名/状态/入参/耗时/指纹短显/进行中 progress）；API 测试覆盖排序与字段
- [x] 4.3 `POST /api/runs/{id}/retry`（复制原实例快照+入参新建 Run）与 `DELETE /api/runs/{id}`（清理报告目录 `ReportService.cleanup_run`）；API 测试覆盖
- [x] 4.4 `GET /api/types`（token + constructible，`constructible = TypeSpec.cast is not None`）；API 测试覆盖内建类型标志
- [x] 4.5 `TreeService.delete` 语义改 SET NULL 保留历史（删树后 runs 仍在、以快照名可查）；API 测试覆盖

## 5. 前端

- [x] 5.1 全局页签导航组件（行为树管理/行为树执行列表/插件管理），"导入行为树"/"新建行为树"移入行为树管理页内容区；组件测试断言导航项与按钮位置（`data-testid`）
- [x] 5.2 接入 `GET /api/types` 动态化 `tokens.ts` + 入参对话框组件（仅可构造类型渲染输入框，缺省值/类型提示）；组件测试覆盖
- [x] 5.3 `RunListPage`：实例表（状态徽章/入参/耗时/指纹短显）+ 进行中轮询（`usePolling`）+ 重试/查看快照/删除；组件测试覆盖渲染与操作
- [x] 5.4 `TreeListPage` 执行按钮约束（无入参直跑/有可构造入参弹对话框/含不可构造入参不渲染按钮）；`RunReportPage` 新增出参区与重试按钮；组件测试覆盖

## 6. E2E（核心用户链路，AGENTS.md 强制）

- [x] 6.1 E2E：树列表带入参执行 → 执行列表出现实例并轮询到终态 → 报告页展示出参（Playwright 驱动真实浏览器）
- [x] 6.2 E2E：对历史实例重试 → 新实例出现且携带相同快照/入参；含不可构造入参的树"执行"按钮不渲染

## 7. 文档同步与验收

- [x] 7.1 更新 `docs/contract.md` §12（执行实例/快照/指纹/队列/入参出参）与 `docs/specs`（M5-orchestrator/M8/M9 相关章节）+ `README.md`；`ruff` 检查通过
- [x] 7.2 全量验证：`pytest`（引擎+服务）、前端 `npm run lint/typecheck/test`、`npm run test:e2e` 全绿；按 AGENTS.md 提交并推送（中文提交信息）