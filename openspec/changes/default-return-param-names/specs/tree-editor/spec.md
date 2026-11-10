## ADDED Requirements

### Requirement: 后端权威文档

编辑器 SHALL 以服务端行为树文档为唯一业务数据源。前端只保留 UI 状态（选中节点、侧栏 Tab、拖拽中状态、文本输入缓冲），所有增删改 MUST 通过后端命令 API 完成，并以响应中的完整文档重绘。

- 新建行为树：进入编辑器时创建草稿，使用临时名称 `未命名-<时间戳>`。
- 查看已有树不改变状态、不创建草稿。
- 对正式树做任何修改 → 同一条记录转草稿。
- 文本输入 SHALL debounce/onBlur 后提交，避免每按键一次请求。

#### Scenario: 新增节点由后端生成
- **WHEN** 用户拖入一个 FunctionCall 节点并选择函数
- **THEN** 后端生成节点 id 与默认接收名/类型，前端渲染响应文档

#### Scenario: 查看不产生草稿
- **WHEN** 用户打开并退出一个正式行为树且未修改
- **THEN** 该树仍为正式版

### Requirement: 默认接收名与类型展示

编辑器 SHALL 展示后端生成的 `ref` / `FunctionCall` 接收名与类型：

- 默认名 `<节点id>_<返回参数名>`；
- 类型来自函数 `returns` 类型 / 目标文档 `outputs` 类型；
- 用户只能编辑名称，类型输入框 MUST NOT 出现；
- 自动名冲突时后端追加 `_1/_2`；
- 不自动改写文档内 `Param.<旧名>` 引用。

#### Scenario: FunctionCall 自动填充
- **WHEN** id 为 `n2` 的节点选择返回 `{status: int, body: str, headers: object}` 的函数
- **THEN** 前端显示 `n2_status: int`、`n2_body: str`、`n2_headers: object`

#### Scenario: ref 自动填充
- **WHEN** id 为 `n3` 的 ref 节点选择 `outputs: {urlText: str}` 的目标文档
- **THEN** 前端显示 `n3_urlText: str`

#### Scenario: 用户改名称
- **WHEN** 用户把 `n2_status` 改为 `code`
- **THEN** 名称变为 `code`，类型仍为 `int`；文档其他位置的 `Param.n2_status` 不被自动改写，保存校验会报告未定义引用

### Requirement: 草稿与正式状态展示

行为树列表 SHALL 显示草稿/正式状态：

- 草稿显示“草稿”徽标；
- 草稿 MUST NOT 显示可执行按钮；
- 删除按钮删除整棵行为树（草稿或正式版同一记录）；
- 保存成功后转为正式版。

#### Scenario: 草稿不可执行
- **WHEN** 列表中存在草稿行为树
- **THEN** 该行不渲染执行按钮

#### Scenario: 保存转正式
- **WHEN** 草稿通过保存校验
- **THEN** 状态变为正式版，列表徽标消失
