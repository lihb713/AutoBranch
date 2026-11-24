# tree-editor Specification

## Purpose

行为树编辑器提供可搜索下拉：函数名选择器罗列全部插件函数的全名（`插件名.函数名`）并支持关键字过滤；ref 目标文档、槽位 / 分支子节点等可能变大的下拉也支持输入过滤，避免用户在长列表中手动翻找。

## Requirements
### Requirement: 可搜索函数名选择器

编辑器 FunctionCall 节点的函数名输入 SHALL 为**可搜索下拉**：罗列全部已注册函数的全名（`插件名.函数名`，如 `compute.add`），附带函数说明；支持输入关键字过滤（前缀 / 包含匹配，如输入 `com` 过滤出 `compute.add` 等）。选择后 FunctionCall 的 `function` 字段 SHALL 保存**全名**。当前值不在清单中时（旧树 / 手输 / 插件已删除）SHALL 仍原样显示并允许保存。

#### Scenario: 搜索并选择函数
- **WHEN** 用户在函数名选择器输入 `com`
- **THEN** 下拉罗列以 `com` 开头的全名（如 `compute.add` / `compute.sum`），选择后 `function` 存全名

#### Scenario: 当前值不在清单中
- **WHEN** 编辑一个 `function` 为未注册全名的 FunctionCall 节点
- **THEN** 选择器仍显示该值，不强制用户重选

### Requirement: 可搜索 ref 目标文档

ref 节点的「目标文档」下拉 SHALL 支持输入过滤（行为树文档名列表可能变大），其余选择行为与原生下拉一致。

#### Scenario: 过滤目标文档
- **WHEN** 用户在 ref 目标文档下拉输入关键字
- **THEN** 下拉只展示匹配的文档名，选择后写入目标文档

### Requirement: 可搜索槽位与分支子节点

槽位挂载子节点与 Branch 分支动作的「子节点」下拉 SHALL 支持输入过滤（游离树根节点列表可能变大），保证「只展示可选选项」的约束不变。

#### Scenario: 过滤游离树根
- **WHEN** 用户在槽位子节点下拉输入关键字
- **THEN** 下拉只展示匹配的游离树根节点，选择后挂载到槽位


### Requirement: 行为树导入与导出

行为树列表 SHALL 支持从 YAML 文件导入行为树，并 SHALL 支持将选中的行为树导出为 YAML 文件。导出内容 SHALL 为该行为树当前完整文档内容（含草稿/正式状态），文件名 SHALL 使用行为树名称并附加 `.yaml` 扩展名。

#### Scenario: 导出行为树
- **WHEN** 用户在行为树列表点击「导出」
- **THEN** 浏览器下载以行为树名命名的 YAML 文件，内容与当前文档一致

#### Scenario: 导入行为树
- **WHEN** 用户选择 YAML 文件导入
- **THEN** 系统解析树名并创建行为树，随后刷新列表


### Requirement: ForEach 节点编辑

前端编辑器 SHALL 支持 ForEach 节点：临时变量名/值行增删改、`on_failure` 选择、`body` 槽位；保存时校验至少一个变量与 body。

#### Scenario: 编辑 ForEach
- **WHEN** 用户添加 ForEach 节点并填写变量/body
- **THEN** 文档保存为 `type: ForEach`，variables/on_failure/body 序列化正确

### Requirement: 复杂值编辑

树编辑器 SHALL 支持 `array`/`object`/`generics`/`page_ref` 类型 token；FunctionCall 必填参数若由 `kwargs` 提供，属性面板入参区 SHALL 回显其值并标注命名参数；Define 的 object/array 值 SHALL 以 JSON 文本编辑并与 YAML dict/list 无损往返。

#### Scenario: 必填 kwargs 回显
- **WHEN** 节点 args 为空、kwargs 含必填参数
- **THEN** 属性面板显示该值，编辑后回写 kwargs

### Requirement: 条件模式编辑器

条件字段 SHALL 提供显式「自然语言 / 谓词表达式」切换。谓词表达式编辑器 SHALL 支持递归添加谓词、ALL、ANY、NOT；只展示用户可见且单返回 bool 的函数；保存前校验空组、空函数、NOT 子项数量等。Branch.when SHALL 以摘要 + 弹窗方式编辑。

#### Scenario: 添加谓词组
- **WHEN** 用户切换到谓词表达式并点击添加 ALL/ANY/NOT
- **THEN** 编辑器生成对应嵌套结构并在保存时写回条件字段


### Requirement: 画布平移与缩略图

行为树画布 SHALL 支持空白处鼠标左键拖拽平移；左下角 SHALL 固定悬浮缩略图及可拖动的当前视口框（不随画布滚动移出视口）；缩放控件保留在右下角。拖拽不得拦截节点点击和画布控件。

#### Scenario: 鼠标拖动画布
- **WHEN** 用户在画布空白处按住左键拖动
- **THEN** 画布滚动位置随鼠标移动，不需要操作滚动条

#### Scenario: 缩略图定位
- **WHEN** 用户拖动缩略图中的视口框
- **THEN** 主画布滚动到对应区域


### Requirement: 行为树描述

行为树 SHALL 支持可选描述信息，用于说明业务目标、适用场景与前置条件。描述 SHALL 在列表以摘要展示、悬浮气泡展示全文，并可在编辑器「树信息」中编辑；描述随保存提交，不写入行为树 YAML 内容。

#### Scenario: 列表查看长描述
- **WHEN** 行为树描述较长
- **THEN** 列表截断显示，悬停时气泡展示完整内容

#### Scenario: 编辑器编辑描述
- **WHEN** 用户在「树信息」填写描述并点击保存
- **THEN** 描述持久化并在列表/编辑器重新加载后显示


### Requirement: ForEach 提前终止与点路径

ForEach SHALL 支持 `break_on_success`：body 成功后提前终止。变量读取 SHALL 支持 `Param.变量.字段` 点路径（dict 键/list 数字索引），用于 FunctionCall/ref/Define 参数与表达式求值。

#### Scenario: 找到首个成功项即停止
- **WHEN** ForEach 设置 break_on_success 且第一个 body 成功
- **THEN** 后续项不再执行

#### Scenario: 读取对象字段
- **WHEN** 参数使用 Param.vm_info.ip
- **THEN** 运行时读取 vm_info 字典的 ip 字段


### Requirement: Action 超时与黑板截断提示

Action 属性面板 SHALL 支持可选节点级 `timeout`。变量黑板 SHALL 对状态 API 标记为截断的变量显示完整长度提示。

#### Scenario: 单独设置 Action 超时
- **WHEN** 用户在 Action 属性面板填写 timeout
- **THEN** 序列化文档包含该字段并覆盖文档/全局超时

#### Scenario: 超长变量截断
- **WHEN** 状态 API 返回 truncated=true
- **THEN** 黑板显示「已截断，完整长度 N 字符」


### Requirement: Parallel 编辑

节点面板 SHALL 提供 Parallel；属性面板 SHALL 支持变量、失败策略、最大并发数与变量冲突策略，并能解析/序列化。

#### Scenario: 编辑并发策略
- **WHEN** 用户设置 max_concurrency=2、on_conflict=last
- **THEN** 文档序列化包含对应字段
