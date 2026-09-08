## Purpose

提供行为树管理系统的后端服务：行为树文档的持久化管理与清晰度校验、执行触发与状态轮询、报告/截图存储与 HTTP 提供，并将引擎作为库内嵌同进程为 M9a 前端提供 REST API。

## ADDED Requirements

### Requirement: 行为树文档 CRUD 管理
系统 SHALL 支持对行为树文档的创建、列表、查看、修改、删除（CRUD），文档以 name（唯一）+ content（yaml 文本）持久化，并返回文档元数据（id、name、created_at、updated_at）。

#### Scenario: 创建文档
- **WHEN** 客户端以合法 name 与 content 调用创建接口 `POST /api/trees`
- **THEN** 系统创建该文档并返回 201，响应含新文档的 id 与元数据

#### Scenario: 列出文档
- **WHEN** 客户端调用列表接口 `GET /api/trees`
- **THEN** 系统返回 200 与文档列表（含各文档 id、name、时间戳）

#### Scenario: 查看单个文档
- **WHEN** 客户端以存在的文档 id 调用 `GET /api/trees/{id}`
- **THEN** 系统返回 200 与该文档完整信息

#### Scenario: 修改文档
- **WHEN** 客户端以存在的文档 id 调用 `PUT /api/trees/{id}` 提交 name/content 变更
- **THEN** 系统更新该文档并返回 200，响应含更新后的元数据

#### Scenario: 删除文档
- **WHEN** 客户端以存在的文档 id 调用 `DELETE /api/trees/{id}`
- **THEN** 系统删除该文档并返回 204

#### Scenario: 访问不存在的文档
- **WHEN** 客户端以不存在的文档 id 调用查看/修改/删除接口
- **THEN** 系统返回 404 与错误信息

#### Scenario: 创建重名文档
- **WHEN** 客户端创建与既有文档重名的文档
- **THEN** 系统返回 409 冲突错误，且不产生新文档

#### Scenario: 提交非法参数
- **WHEN** 客户端提交空 name、超长 name 或缺失 content
- **THEN** 系统返回 422 校验错误，且不写入任何数据

### Requirement: 保存时清晰度校验
系统 SHALL 在保存行为树文档时复用 M2 解析器执行清晰度校验（结构合法、展开后合法、块引用存在、循环有上界、变量契约一致、动作可定位、有验证条件、条件谓词可校验，见契约 §4.4）；校验失败时拒绝保存并返回可读的错误清单（CheckReport）供用户修正。

#### Scenario: 保存合法文档
- **WHEN** 客户端保存通过 M2 清晰度校验的文档
- **THEN** 系统保存成功并返回 201/200，不附带校验错误

#### Scenario: 保存非法文档被拒绝
- **WHEN** 客户端保存不满足任一清晰度校验项（如结构不合法、块引用缺失、循环无上界）的文档
- **THEN** 系统返回 422，detail 携带 CheckReport 错误清单，且文档不被保存

#### Scenario: 校验错误清单可读
- **WHEN** 非法文档被拒绝保存时返回错误清单
- **THEN** 错误清单逐条列出违规项及定位（结构/引用/循环/变量契约/可定位/验证条件/谓词等类别）

### Requirement: 执行前再校验
系统 SHALL 在触发执行前对目标文档再次执行清晰度校验；校验不通过的文档不得进入执行，且该次执行被拒绝。

#### Scenario: 执行前文档已损坏被拒绝
- **WHEN** 客户端对校验不通过的文档触发执行
- **THEN** 系统拒绝执行并返回 422 携带校验错误清单，不产生 run_id

#### Scenario: 执行前校验通过正常触发
- **WHEN** 客户端对执行前校验通过的文档触发执行
- **THEN** 系统创建一次执行并返回 run_id

### Requirement: 异步执行触发
系统 SHALL 支持以 `POST /api/trees/{id}/run` 异步触发执行：立即返回 202 与 run_id，不阻塞等待执行完成；执行在内嵌引擎 M7 中后台运行，同一文档同时只允许一个进行中的执行。

#### Scenario: 触发执行返回 run_id
- **WHEN** 客户端对存在且校验通过的文档调用执行触发接口
- **THEN** 系统立即返回 202 与唯一 run_id

#### Scenario: 重复触发进行中的执行
- **WHEN** 客户端对已有进行中执行的文档再次触发执行
- **THEN** 系统返回 409 冲突错误，不产生新的执行

#### Scenario: 触发不存在的文档
- **WHEN** 客户端对不存在的文档调用执行触发接口
- **THEN** 系统返回 404

### Requirement: 执行状态数据契约 ExecState
系统 SHALL 以 ExecState 契约输出执行状态，字段为 run_id、progress（0.0~1.0）、current_node（当前节点信息或空）、completed（已完成节点报告列表）、finished（是否结束），供前端轮询消费。

#### Scenario: 输出标准状态字段
- **WHEN** 客户端查询任意 run 的执行状态
- **THEN** 响应包含 run_id、progress、current_node、completed、finished 全部字段且类型符合契约

#### Scenario: 状态字段实时更新
- **WHEN** 执行推进期间客户端轮询状态
- **THEN** progress 单调增长，current_node 反映当前执行节点，completed 随完成节点增加

#### Scenario: 状态含失败原因
- **WHEN** 执行以失败结束
- **THEN** finished 为 true，且状态携带 failure_reason 说明失败原因

### Requirement: 执行状态轮询 API
系统 SHALL 提供 `GET /api/runs/{run_id}/state` 供前端每秒轮询执行状态；对不存在的 run_id 返回 404；执行结束（success/failure）后状态保持可查询。

#### Scenario: 轮询未完成执行
- **WHEN** 客户端在引擎执行过程中轮询 `/api/runs/{run_id}/state`
- **THEN** 系统返回 200 与当前 ExecState，finished 为 false，含当前进度与已完成节点

#### Scenario: 轮询已结束执行
- **WHEN** 客户端在执行结束后轮询 `/api/runs/{run_id}/state`
- **THEN** 系统返回 200，finished 为 true，completed 含全部节点报告

#### Scenario: 轮询不存在的 run
- **WHEN** 客户端轮询不存在的 run_id
- **THEN** 系统返回 404

### Requirement: 执行报告与回溯报告获取
系统 SHALL 在执行结束后提供完整执行报告（`GET /api/runs/{run_id}/report`）与回溯报告（`GET /api/runs/{run_id}/trace`）；执行未结束时返回进行中状态而非最终报告。

#### Scenario: 获取已完成执行报告
- **WHEN** 客户端在执行结束后获取 `/api/runs/{run_id}/report` 与 `/api/runs/{run_id}/trace`
- **THEN** 系统返回 200 与完整执行报告、回溯报告

#### Scenario: 执行中获取报告
- **WHEN** 客户端在执行进行中获取报告接口
- **THEN** 系统返回进行中状态标识，不返回最终报告内容

### Requirement: 报告/截图文件 HTTP 提供
系统 SHALL 将执行产生的报告与截图文件持久化落盘（`data/reports/`），库中仅存相对路径，并经 `GET /api/reports/{path}` 以 HTTP 提供；路径解析必须做白名单校验，杜绝目录穿越。

#### Scenario: 正常提供报告文件
- **WHEN** 客户端请求已存在的报告相对路径
- **THEN** 系统返回 200 与文件内容（按文件类型提供合适 MIME）

#### Scenario: 拒绝目录穿越请求
- **WHEN** 客户端请求含 `..` 或逃逸存储根目录的路径
- **THEN** 系统返回 400/404，不暴露存储根之外的文件

#### Scenario: 请求不存在的报告文件
- **WHEN** 客户端请求存储根内不存在的报告路径
- **THEN** 系统返回 404

### Requirement: 引擎内嵌同进程集成
系统 SHALL 将 M7 引擎作为 Python 库内嵌于同一进程调用（`engine.run()` 与 `get_exec_state()`），与执行任务共享内存、行为树对象与报告数据直接传递，不进行序列化传输与进程间通信（契约 §12.3）。

#### Scenario: 引擎以库形式被调用
- **WHEN** 系统触发执行与查询状态
- **THEN** 均在当前进程内直接调用 M7 引擎入口，无外部进程与序列化边界

#### Scenario: 状态查询无需复制数据
- **WHEN** 执行状态被查询
- **THEN** 系统直接读取引擎内存中的执行状态，无需跨进程传输