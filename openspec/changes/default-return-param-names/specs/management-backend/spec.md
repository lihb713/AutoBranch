## ADDED Requirements

### Requirement: 行为树草稿/正式状态

`trees` SHALL 增加状态 `status ∈ {draft, published}`，历史记录迁移为 `published`。

- 新建草稿 API SHALL 创建 `draft` 记录，名称使用 `未命名-<时间戳>`。
- 对 `published` 的任何编辑命令 SHALL 将同一记录置为 `draft`。
- 删除行为树 SHALL 删除该记录（草稿或正式版）。
- 列表/详情 API SHALL 返回状态。

#### Scenario: 新建草稿
- **WHEN** 调用新建草稿 API
- **THEN** 返回 `status=draft`，名称为临时名，初始为空树文档

#### Scenario: 编辑正式树变草稿
- **WHEN** 对 `published` 树提交编辑命令
- **THEN** 同一记录状态变为 `draft`，不产生第二棵树

### Requirement: 命令式编辑 API

后端 SHALL 提供命令接口修改草稿文档并返回完整文档：

- `add_node {type}`：后端生成 ASCII 节点 id；Step 自动附带 Action。
- `delete_node {node_id, subtree}`：后端实现单节点/子树删除语义。
- `update_node {node_id, patch}`：后端应用结构/字段/函数/目标/参数/返回值变更并归一化。
- `update_doc {patch}`：更新 `tree`/`inputs`/`outputs`/`config`。

命令执行后 SHALL 归一化默认接收名/类型；草稿允许未通过完整校验。

#### Scenario: 添加节点返回完整文档
- **WHEN** 提交 `add_node {type: "Action"}`
- **THEN** 响应包含新节点 id 和完整正文；状态为 draft

#### Scenario: 选择函数填充默认返回值
- **WHEN** 对 FunctionCall 节点提交 `update_node` 设置 `function`
- **THEN** 响应中该节点 `returns` 已按函数声明填充名称与类型

### Requirement: 保存发布与执行限制

- `POST /api/trees/{id}/save` SHALL 校验完整清晰度；成功后更新名称、状态置 `published`；失败 422 且保持 `draft`。
- `POST /api/trees/{id}/run` SHALL 拒绝 draft（409/422）。
- 只有 `published` 可作为 ref 目标；解析/执行时目标为 draft MUST 失败。

#### Scenario: 保存失败保持草稿
- **WHEN** 草稿存在未定义变量引用时保存
- **THEN** 返回校验问题，状态仍为 draft

#### Scenario: 草稿不可执行
- **WHEN** 对 draft 树调用 run
- **THEN** 返回错误，不创建 Run

#### Scenario: ref 目标为草稿
- **WHEN** 引用目标文档处于 draft
- **THEN** 清晰度校验失败并提示目标尚未保存为正式版
