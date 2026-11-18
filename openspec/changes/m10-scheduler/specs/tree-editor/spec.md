# tree-editor delta · M10

## ADDED Requirements

### Requirement: 行为树导出

行为树列表 SHALL 支持将选中行为树导出为 YAML 文件，内容为当前完整文档（草稿/正式版均可），文件名使用行为树名并附加 `.yaml`。

#### Scenario: 导出行为树

- **WHEN** 用户在行为树列表点击「导出」
- **THEN** 浏览器下载以行为树名命名的 YAML 文件，内容与当前文档一致
