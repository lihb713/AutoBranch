## ADDED Requirements

### Requirement: 文件插件模块化

`file` 插件 SHALL 提供：
- 文件管理 API：`GET/POST /api/plugins/file/files`、`GET /api/plugins/file/files/{id}`、`GET .../download`、`DELETE .../{id}`；
- 模型 `plugin_file_records`；
- 存储目录 `autobranch/plugins/file/data/`；
- 配置 `max_file_size`（MB）；
- 前端清单 `{route:/file,label:文件管理,component:FileManager}`。

上传超过配置上限 MUST 返回 413。
