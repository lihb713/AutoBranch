## Purpose

为 WebOps 提供纯前端用户界面（M9a）：拖拽式行为树编辑器（产出含复合节点的行为树文档）、行为树管理 CRUD、保存时清晰度校验提示，以及以 1 秒轮询实时渲染节点进度与截图、展示完整执行与回溯报告的执行报告页，全部能力消费 M9b 后端 API 实现。

## ADDED Requirements

### Requirement: 拖拽式行为树编辑器

系统 SHALL 提供行为树编辑器，支持用户以拖拽方式将节点加入行为树并填写节点信息；编辑器 SHALL 支持节点类型 Step、Branch、LoopUntil、IfThenElse、Retry、Sequence 与 ref 块引用（契约 §4.3），并为叶子节点提供自然语言内容填写（action/expect/when/until 等）。系统 SHALL 根据编辑内容生成合法的行为树 yaml 文档文本，供后端保存与校验。

#### Scenario: 拖拽节点创建行为树

- **WHEN** 用户从节点面板拖拽一个复合节点到画布中
- **THEN** 该节点出现在行为树视图中，且可继续在其中添加子节点

#### Scenario: 填写节点信息

- **WHEN** 用户选中某个节点并填写其自然语言内容（如 Step 的 action 与 expect、LoopUntil 的 until 与 max）
- **THEN** 该节点的信息被保存到编辑器内部状态，且展示反映最新填写内容

#### Scenario: 生成含复合节点的行为树文档

- **WHEN** 用户在编辑器中完成节点组织与信息填写并请求生成文档
- **THEN** 系统输出合法的行为树 yaml 文档，其中复合节点（Step/Branch/LoopUntil/IfThenElse/Retry/Sequence/ref）保持为书写形态、不展开为基础节点

#### Scenario: 编辑已存在的行为树

- **WHEN** 用户打开一份已保存的行为树进行修改
- **THEN** 编辑器加载该树的复合节点视图，修改后的文档在生成时可被重新生成

### Requirement: 多块文档编辑器（方案 2）

系统 SHALL 支持编辑含多个块的行为树文档（契约 §4.1：1 主块 + N 附属块）。编辑器 SHALL 以块列表面板展示主块（标「主」）与全部附属块，支持切换当前编辑块、新建附属块与删除附属块（主块不可删）；保存时 SHALL 保留全部块与各块声明（inputs/outputs/config）。无 `block` 前缀的裸树文档（整文档即主块）SHALL 被兼容加载与保存。

#### Scenario: 加载多块文档展示块列表

- **WHEN** 用户打开一份含多个 `block` 定义的行为树文档
- **THEN** 编辑器展示块列表面板（主块标「主」+ 附属块），默认编辑主块，画布显示主块的行为树

#### Scenario: 切换编辑块

- **WHEN** 用户点击块列表中某块
- **THEN** 编辑器切换为编辑该块，画布显示该块的行为树

#### Scenario: 新建附属块

- **WHEN** 用户点击「新建块」并输入块名
- **THEN** 编辑器新建该附属块（空 Sequence）并切换编辑它，保存时随文档一并输出

#### Scenario: 删除附属块

- **WHEN** 用户删除一个非主块
- **THEN** 该块从文档移除；主块不可删除

#### Scenario: 保存保留全部块与声明

- **WHEN** 用户保存含多块与块声明的文档
- **THEN** 序列化输出保留主块、全部附属块及各块声明（inputs/outputs/config）

#### Scenario: 裸树兼容

- **WHEN** 用户打开一份无 `block` 前缀的裸树文档
- **THEN** 编辑器按主块加载（整文档即主块行为树），保存时保持裸树形态

### Requirement: 复合节点视图

系统 SHALL 在编辑、查看与执行报告等所有用户界面中，始终以含复合节点的行为树形式呈现（Step/Branch/LoopUntil/IfThenElse/Retry/Sequence/ref，契约 §12.5/§4.3）；引擎基础节点（Sequence 展开后的 Action/Condition/Selector/Repeat 等）对用户不可见。系统 SHALL 不在前端展开复合节点，展开与校验由后端完成。

#### Scenario: 编辑器仅展示复合节点

- **WHEN** 用户编辑一份行为树
- **THEN** 界面上仅呈现复合节点（Step/Branch/LoopUntil/IfThenElse/Retry/Sequence/ref），不展示引擎基础节点

#### Scenario: 加载行为树保持复合节点形态

- **WHEN** 用户加载一份以复合节点书写的已保存行为树
- **THEN** 视图中的节点类型与文档书写形态一致，不出现前端展开的基础节点

### Requirement: 行为树管理 CRUD

系统 SHALL 提供行为树管理能力：列表、创建、查看、修改与删除，分别消费 M9b 管理 API `GET/POST /api/trees`、`GET/PUT/DELETE /api/trees/{id}`（契约 §12.2-M9a）。创建与修改成功后系统 SHALL 以服务端返回的最新记录刷新界面。

#### Scenario: 列表展示行为树

- **WHEN** 用户进入行为树管理页
- **THEN** 系统调用列表接口并展示全部行为树记录（名称与更新时间等），空列表时展示空状态提示

#### Scenario: 创建行为树

- **WHEN** 用户在编辑器中完成文档并保存为新行为树
- **THEN** 系统调用创建接口，成功后列表中出现该记录

#### Scenario: 查看行为树

- **WHEN** 用户点击列表中的一条行为树
- **THEN** 系统调用查看接口并在编辑器中展示该树的复合节点视图

#### Scenario: 修改行为树

- **WHEN** 用户修改已存在行为树的名称或内容并保存
- **THEN** 系统调用修改接口，成功后以服务端返回的最新记录更新界面

#### Scenario: 删除行为树

- **WHEN** 用户对某条行为树执行删除
- **THEN** 系统调用删除接口，成功后该记录从列表移除

#### Scenario: 资源不存在时给出错误提示

- **WHEN** 查看/修改/删除的行为树在服务端不存在（404）
- **THEN** 系统向用户展示友好错误提示，不导致页面崩溃

### Requirement: 保存时清晰度校验提示

系统 SHALL 在保存行为树前调用清晰度校验接口 `POST /api/trees/{id}/check`（M9b 复用 M2，契约 §12.5/§4.4）。校验通过时继续保存；校验失败时系统 SHALL 阻止本次保存，并以友好的可读错误清单提示用户定位并修正文档问题。

#### Scenario: 校验通过后保存

- **WHEN** 用户保存一份清晰度校验通过的行为树
- **THEN** 系统完成保存，界面给出保存成功反馈

#### Scenario: 校验失败提示并阻止保存

- **WHEN** 用户保存的行为树未通过清晰度校验（如块引用缺失、循环缺少上界、步骤缺少验证条件）
- **THEN** 系统不执行保存，并展示可读的错误清单提示用户修正

### Requirement: 执行触发与实时状态轮询渲染

系统 SHALL 在用户点击执行时调用 `POST /api/trees/{id}/run` 获取 run_id，然后每 1 秒轮询 `GET /api/runs/{run_id}/state`（契约 §12.4）。轮询期间系统 SHALL 实时渲染执行进度、当前执行节点与已完成节点的成功/失败状态，并展示各节点的截图；当状态表明执行已结束时系统 SHALL 停止轮询并展示完整执行报告。

#### Scenario: 触发执行并获取 run_id

- **WHEN** 用户对某行为树点击执行
- **THEN** 系统调用执行接口并得到 run_id，随后进入轮询

#### Scenario: 轮询期间实时更新节点进度与截图

- **WHEN** 执行进行中，轮询接口持续返回进度、当前节点与已完成节点报告
- **THEN** 界面每秒更新：节点按 SUCCESS（绿）/FAILURE（红）/RUNNING（蓝）着色，当前执行节点高亮，已完成节点的截图被加载展示

#### Scenario: 执行完成停止轮询

- **WHEN** 轮询接口返回执行已结束（finished 为真）
- **THEN** 系统停止后续轮询请求，并切换到完整执行报告展示

#### Scenario: 轮询接口失败给出提示

- **WHEN** 某次轮询请求失败
- **THEN** 系统向用户展示轮询错误提示，并保持当前已渲染的执行状态

### Requirement: 执行报告与回溯报告展示

系统 SHALL 在执行结束后调用 `GET /api/runs/{run_id}/report` 与 `GET /api/runs/{run_id}/trace`（契约 §5.8.3），分别展示完整执行报告与回溯报告；报告中的截图与文件 SHALL 通过 `GET /api/reports/{path}` 加载展示。

#### Scenario: 展示完整执行报告

- **WHEN** 一次执行结束后用户查看该次执行
- **THEN** 系统加载并展示完整执行报告（各节点结果与截图等）

#### Scenario: 展示回溯报告

- **WHEN** 用户请求查看一次已结束执行的回溯报告
- **THEN** 系统加载并展示回溯报告内容

#### Scenario: 报告文件加载失败时降级提示

- **WHEN** 报告或截图文件经报告文件接口加载失败
- **THEN** 系统保留报告文字内容并在对应位置展示加载失败占位提示