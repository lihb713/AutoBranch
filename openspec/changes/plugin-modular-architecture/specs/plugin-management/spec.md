## ADDED Requirements

### Requirement: 插件 Manifest 与配置

系统 SHALL 提供 `GET /api/plugins?include_manifest=true`、`GET /api/plugins/{name}/manifest`、`GET/PUT /api/plugins/{name}/config`、`GET /api/plugins/{name}/functions`。插件配置 MUST 持久化到 `plugins.config` 并在启动时应用。

- 场景：批量列表一次返回 manifest，避免 N 次请求。
- 场景：修改配置后重启服务仍生效。
