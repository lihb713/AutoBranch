# run-instances-list 提案

## Why

当前一次"执行"只是瞬态：树列表点执行直接跳转报告页，跑完即"消失"，无法回看历史、无法按当时内容重跑、无法为行为树提供入参/查看出参；同一棵树并发被 D8 硬性拒绝（409）。用户需要把"执行"升级为**可管理的执行实例**——保存执行时的行为树快照与入参，支持并发执行、队列调度、历史回看与按快照重试。

## What Changes

- **执行快照（核心）**：`Run` 表新增 `content_snapshot` / `tree_name_snapshot` / `tree_content_hash` / `inputs` / `outputs` 列。触发时刻冻结行为树内容与入参，**执行与重试一律基于该实例的快照**，不读实时树内容（避免排队中/执行中被编辑污染）。实例身份 = `tree_content_hash`（短显 `#a3f9c1`）+ 归一化 `inputs` 直比。
- **`tree_content_hash` = 执行结构指纹**：代表行为树的**执行结构**——相同入参 + 相同哈希 + 外部条件不变 ⇒ 执行结果理论相同。因此只计入影响执行结果的内容，凡不影响执行的一律剔除（解析后取 `nodes`+`root` 的规范序列化哈希，注释/空白/键顺序不参与）：
  - **计入**：根指针 `root`；每节点 `type`；叶子执行内容（Action/Condition 的 `description`/`css_hint`/`set_targets`）；结构槽位与控制字段（`body`/`actions`/`action`/`expect`/`if`/`then`/`else`/`branches`/`until`/`max`）；ref 的 `target`/`args`/`returns`；FunctionCall 的 `function`/`args`/`returns`；槽位引用的节点 id（结构边）；文档级全局配置覆盖（`timeout`/`retry`/`browser`，影响执行）。
  - **剔除**：树名 `tree:`；文档级 `inputs`/`outputs` 声明（`outputs` 是执行结果、随系统外部状态如网页数据变化而变，同树同入参也可能不同，无比较意义）；每节点 `name`（代码确认：报告与控制流均不依赖节点名，仅显示用途）。
  - **与入参无关、与树名无关**：改名或改入参声明不改变哈希，增删改节点或其内容（含执行配置）才改变；树走 A→B→A 改回后老实例哈希可重新匹配。
  - 节点 id 计入（节点池键 + 边引用地址）；纯 id 改名视为不同结构，仅产生安全的"漏匹配"，绝不产生错误的经验复用。
- **历史自包含**：`Run.tree_id` 由 `ondelete="CASCADE"` 改为 `nullable=True` + `ondelete="SET NULL"`——删除行为树后执行历史保留（列表用快照名展示，tree_id 仅承担"当前树仍存在时的编辑跳转"）。
- **根级入参**：`POST /trees/{id}/run` 接受可选 `inputs`，引擎把值 coerce 到声明类型后注入根帧（补全现有"只有类型声明、无值注入"的半成品）；出参在运行结束后读根帧输出、落入 `RunResult.outputs` 并落库。
- **类型可构造性单点派生**：可构造性判定由后端类型系统单点给出——`TypeSpec.cast is not None` 即可由文本构造（str/int/float/bool，入参序列化串经现有 `coerce` 转成类型），`page_ref`/`object` 不可构造；新增 `GET /api/types`（token + constructible）暴露，前端 type token、入参表单、执行按钮约束全部自此派生（不硬编码白名单）。设计上不排除未来新增类型（届时 API 自动反映），但不引入用户自定义类型注册机制（当前无使用者，YAGNI）。
- **不可构造入参禁直接执行**：树声明含不可由文本构造的入参（如 `page_ref`）时，前端"执行"按钮不渲染、后端 `POST /run` 返回 422——该树仅能经 `ref` 由其他树调用（运行时由调用方提供变量值）。
- **执行列表**：新增 `GET /api/runs` 列表接口与 `/runs` 前端页面——状态徽章、树名（快照）、入参、开始/耗时、快照哈希；进行中/排队中行轮询刷新；提供"重试"（复制该实例快照+入参新建 Run）与"查看快照"（展开显示该实例实际执行的内容）。
- **前端导航重构**：右上角新增全局页签导航（行为树管理 / 行为树执行列表 / 插件管理），用于页面切换；"导入行为树"、"新建行为树"等**页面内操作按钮移入对应页面内容区**（如行为树管理页列表上方），不占用页签栏。
- **队列调度**：去掉 D8 同树并发限制，改为全局并发上限 + FIFO 队列——`pending` 即排队中（列表显示序号），并发上限经配置项 `max_concurrent_runs`（默认 3，用户可调）控制，`start` 与每次 run 结束后触发调度；重启恢复沿用现有 `mark_interrupted`（排队中/执行中置 interrupted）。
- **出参展示**：报告页新增"出参"区展示本次运行返回值。

**BREAKING**：`POST /trees/{id}/run` 对含不可构造入参的树由"可执行"改为 422 拒绝；`Run.tree_id` 删除树时不再级联删除历史（由 SET NULL 保留）。

## Capabilities

### New Capabilities

- `run-instances`: 执行实例的管理能力——快照语义执行、根级入参注入与出参返回、类型可构造性单点判定（`GET /api/types`）、执行列表与轮询、FIFO 队列调度、按快照重试、历史自包含保留。覆盖管理后端 runs API/数据模型与前端列表/对话框/出参展示，以及引擎运行入口的入参/出参扩展。

### Modified Capabilities

- `orchestrator`: 引擎运行入口 SHALL 接收根级入参值（coerce 后注入根帧）并在运行结束后返回出参（`RunResult.outputs`）。

## Impact

- **引擎层**：`autobranch/orchestrator/{engine,context,models}.py`（run 接受输入值、返回 outputs；RunResult 扩展）。
- **管理后端 M8**：`server/models/run.py`（快照/入参/出参列 + tree_id SET NULL）、`server/services/runs.py`（快照语义执行、入参校验、队列调度、列表/重试/删除）、`server/routers/runs.py`（新增列表/详情 API）、新增 `GET /api/types` 路由与 service、`server/schemas/run.py`、`server/config.py`（`max_concurrent_runs`）。
- **前端 M9**：`App.tsx`（新增 `/runs` 路由 + 全局页签导航组件）、`TreeListPage`（导入/新建按钮移入页内、入参对话框/不可构造隐藏执行，可构造性自 `GET /api/types` 派生）、新 `RunListPage`、`RunReportPage`（出参区）、`api/runs.ts`、`api/types.ts`、`types/run.ts`、`tokens.ts`（type token 动态化）。
- **E2E**：带入参执行 → 列表出现 → 轮询 → 报告出参 → 重试（复用快照）。
- **文档**：`docs/contract.md` §12、`docs/specs/M5-orchestrator.md`、M8/M9 相关章节；`docs/contract.md` 与模块 spec 同步更新。

**依赖**：Change C（`experience-feedback`）复用 `tree_content_hash` + 归一化 `inputs` 作为经验匹配钥匙。本 Change 为 C 提供 `content_snapshot`/`tree_content_hash`/`inputs` 数据基础。