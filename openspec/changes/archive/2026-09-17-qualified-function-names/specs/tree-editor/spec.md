## Purpose

行为树编辑器提供可搜索下拉：函数名选择器罗列全部插件函数的全名（`插件名.函数名`）并支持关键字过滤；ref 目标文档、槽位 / 分支子节点等可能变大的下拉也支持输入过滤，避免用户在长列表中手动翻找。

## ADDED Requirements

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