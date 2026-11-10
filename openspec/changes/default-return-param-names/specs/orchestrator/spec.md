## ADDED Requirements

### Requirement: ref 仅允许正式文档

ref 解析与执行 SHALL 只允许目标行为树为 `published` 状态。目标为 `draft` 时 MUST 返回清晰错误，不进入子文档执行。

#### Scenario: 引用正式文档
- **WHEN** ref 目标文档状态为 published
- **THEN** 正常加载并执行

#### Scenario: 引用草稿文档
- **WHEN** ref 目标文档状态为 draft
- **THEN** 校验/执行失败并提示“目标行为树尚未保存为正式版”
