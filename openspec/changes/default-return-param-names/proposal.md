## Why

当前 `ref` / `FunctionCall` 的接收变量必须由用户手工填写，漏填时对应返回值被静默丢弃；同时接收变量还要求用户在 UI 中选择类型，而类型本应由函数定义或 ref 目标文档的输出声明决定。随着函数/节点返回参数变多，要求用户逐项填写名称和类型不可持续。

同时，编辑器当前是“前端本地文档 + 保存时上传”，默认名、类型、校验、历史迁移容易在前后端产生分叉。我们决定把行为树文档的增删改统一收敛到后端：前端只负责展示与交互，后端是唯一文档权威。

## What Changes

### 1. 默认接收名与类型

- 为 `ref` / `FunctionCall` 自动生成接收名：`<节点id>_<返回参数名>`（如 `n2_status`、`n3_stdout`）。
- 接收类型由**来源声明**决定：
  - `FunctionCall`：插件函数 `FunctionDef.returns`（带类型）；
  - `ref`：目标文档 `outputs`（带类型）。
- 用户只能修改接收名，**不能修改类型**；类型随函数/目标自动更新。
- 冲突只针对自动生成名：从 `_1` 开始追加后缀（`n2_status_1`、`n2_status_2`）；冲突变量删除后不回退原名。
- 不自动改写文档内 `Param.<旧名>` 引用；改名后由保存校验发现未定义引用，用户自行修正。

### 2. 返回类型进入声明

- **BREAKING** `FunctionDef.returns` 从名字元组改为 `{名称: 类型}` 映射；自定义插件强制带类型。
- **BREAKING** 文档 `outputs` 从名字列表改为 `{名称: 类型}` 映射。
- 所有参数名与节点 id 强制裸 ASCII 标识符 `[A-Za-z_][A-Za-z0-9_]*`：
  - `inputs` 键、`outputs` 键、`FunctionDef.returns` 名称、节点 id、`returns` 接收名。
  - `tree` 文档名与节点显示名 `name` 保持中文，不受影响。

### 3. 后端权威文档 + 单文档草稿状态

- 一棵树只有**一个文档**，状态为 `draft` 或 `published`（不存在“正式+草稿副本”）。
- 新建行为树：后端立即创建 `draft`，使用临时名称 `未命名-<时间戳>`；首次保存校验通过后改名为用户填写名称并转为 `published`。
- 查看已有树不改变状态；对 `published` 做任何增删改立即变为 `draft`（同一记录）。
- 只有 `published` 可执行；`draft` 不显示执行按钮。
- `ref` 只允许引用 `published` 文档；目标为 `draft` 时校验/执行失败。
- 草稿允许未通过校验；保存时统一校验，失败保持草稿。
- 删除草稿或正式版都是删除该行为树记录，没有“放弃草稿保留正式版”。

### 4. 命令式编辑 API

- 前端不再计算节点结构/默认名/类型/槽位/删除语义；通过命令接口提交操作，后端修改文档并返回完整文档。
- 命令包括：新建草稿、添加节点、删除节点、更新节点、更新文档接口/名称。
- 文本输入在前端 debounce/onBlur 后提交。
- 迁移脚本与运行前兜底复用同一后端归一化服务。

## Capabilities

### Modified Capabilities

- `behavior-tree-parser`：节点 id / inputs / outputs ASCII 校验；outputs 带类型映射；ref 对齐校验更新。
- `plugin-system`：`FunctionDef.returns` 带类型且强制合法；注册/校验时拒绝非法返回声明。
- `tree-editor`：后端权威文档、命令式编辑、草稿状态、默认名/类型展示、去除类型编辑。
- `management-backend`：草稿/正式状态、命令 API、保存发布、仅正式可执行、ref 仅正式。
- `orchestrator`：ref 解析/执行仅允许 published 目标。

## Impact

- 后端：`plugin_system`（returns 类型）、`parser`（outputs/ASCII）、`server`（Tree 状态、命令 API、归一化、迁移）、`orchestrator`（published 检查）。
- 前端：编辑器改为命令驱动；列表增加草稿徽标与执行限制；移除类型下拉。
- 数据：`trees` 增加状态列；历史 `trees.content` 迁移（ASCII、typed outputs、默认返回名）；清空 `experiences`；`runs.content_snapshot` 保持不变。
- 文档：`docs/contract.md`、`docs/specs/M1/M3/M7/M8/M9`、`docs/user-guide.md`、`README.md`。
