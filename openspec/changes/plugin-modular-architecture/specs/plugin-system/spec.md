## ADDED Requirements

### Requirement: 插件模块化扩展

插件 SHALL 可选实现 `register_routes` / `register_models` / `frontend_manifest` / `storage_dir` / `config_schema` / `get_config` / `set_config` / `release`，默认空实现，纯函数插件无需改动。

- 场景：插件声明 `register_routes` → 启动时 ensure_loaded 并注册 `/api/plugins/{name}/` 路由。
- 场景：插件声明 `register_models` → 在 create_all 前 import 模型并建表。
- 场景：插件声明 `frontend_manifest` → 列表 API 附带页面清单。
- 场景：插件声明 `config_schema` → 配置 API 与持久化生效。
