## Context

见 `proposal.md`。当前架构只有函数注册；`create_app()` 先 `configure_database` 建核心表，插件后加载。

## Decisions

### D1. 可选扩展、默认空实现

`PluginBase` 新增方法/属性均为可选，默认 no-op/None；纯函数插件无需改动。

### D2. 启动顺序

`create_app()`：加载插件 → `init_builtins`（含自定义插件）→ 遍历 `register_models(Base)` → `create_all_tables()` → 仅对重写 `register_routes` 的插件 `ensure_loaded` + 注册路由。单插件失败写 stderr 不阻断启动。

### D3. 配置持久化

`plugins.config`（JSON 文本）保存配置；启动加载插件后调用 `set_config`；`PUT /config` 应用并落库。避免重启丢失。

### D4. 插件路由/模型/存储/前端命名

- API 前缀 `/api/plugins/{name}/`
- 表前缀 `plugin_{name}_`
- 存储目录 `autobranch/plugins/{name}/{storage_dir}/`（插件 init 创建）
- 前端页面从插件列表页进入，不加入全局导航；组件名静态映射（安全，不支持自定义插件远程组件）。

### D5. file 插件

`FileService` 统一管理 `plugins/file/data/`；上传大小受 `max_file_size` 配置限制；`plugin_file_records` 存元数据；API 提供列表/上传/详情/下载/删除。

## Risks

- 插件模型导入可能循环导入 → `server/__init__.py` 延迟导入。
- 文件上传依赖 `python-multipart`。
- 插件路由与核心 `/api/plugins/{name}` 路由共存，路径不冲突。
