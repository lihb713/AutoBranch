## REMOVED Requirements

### Requirement: 浏览器会话生命周期与冷启动
**Reason**: 浏览器驱动并入 `browser-plugin`，不再是独立能力。
**Migration**: 作为浏览器插件内部实现。

### Requirement: 页面打开与页面引用
**Reason**: 并入 `browser-plugin`。
**Migration**: 作为浏览器插件内部实现（`open` 返回页面对象）。

### Requirement: 页面引用与操作绑定
**Reason**: 并入 `browser-plugin`。
**Migration**: 作为浏览器插件内部实现（当前活动页由插件维护）。

### Requirement: 页面操作函数
**Reason**: 并入 `browser-plugin`（作为插件函数）。
**Migration**: 迁入 `browser-plugin`。

### Requirement: 文件函数
**Reason**: 文件能力独立为 `file-plugin`。
**Migration**: 迁入 `file-plugin`。

### Requirement: HTTP 监听
**Reason**: 并入 `browser-plugin`。
**Migration**: 作为浏览器插件内部实现。

### Requirement: 独立 HTTP 请求
**Reason**: 并入 `browser-plugin`。
**Migration**: 作为浏览器插件内部实现。

### Requirement: 页面截图
**Reason**: 截图改为在 `semantic_graph`（"看页面"）时由浏览器插件产出并写入报告。
**Migration**: 迁入 `browser-plugin`，不再由编排器无条件截。

### Requirement: DOM 爬取
**Reason**: 并入 `browser-plugin`（语义图内部）。
**Migration**: 作为浏览器插件内部实现。

### Requirement: 操作结果与错误语义
**Reason**: 并入 `browser-plugin` / `plugin-system`。
**Migration**: 作为插件分发与结果语义。
