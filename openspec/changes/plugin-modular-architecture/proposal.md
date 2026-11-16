## Why

当前插件只是 Python 函数集合，无法提供后端 API、前端页面、数据库模型、存储目录和配置项；插件管理页也只支持源码查看。需要把插件升级为可选的「功能模块」，同时保持纯函数插件向后兼容。

## What Changes

- `PluginBase` 新增可选扩展：`register_routes` / `register_models` / `frontend_manifest` / `storage_dir` / `config_schema` / `get_config` / `set_config` / `release`。
- 服务启动时注册插件模型并建表、注册插件路由；插件 API 前缀 `/api/plugins/{name}/`，表前缀 `plugin_{name}_`。
- 插件配置 API 与持久化（`plugins.config`）；插件列表支持 `include_manifest=true` 批量返回 manifest。
- 插件函数详情 API 暴露全部函数（含 LLM-only/output_param/可见性）。
- `file` 插件模块化：文件管理 API、`plugin_file_records` 表、`data/` 存储、配置 `max_file_size`、前端文件管理页面。
- 前端插件管理升级：卡片列表、函数详情/源码双 Tab、配置弹窗、插件前端页面动态路由（仅从插件列表进入）。
- `server/__init__.py` 延迟导入，修复插件模型导入 `autobranch.server.db` 的循环导入。

## Impact

后端 `plugin_system` / `server` / `plugins/file`；前端插件管理、动态路由、文件管理页；文档 specs 与 openspec。
