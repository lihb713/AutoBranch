## REMOVED Requirements

### Requirement: 工具函数注册表
**Reason**: 由 `plugin-system` 取代——统一函数注册表 + 插件框架。
**Migration**: 工具函数改为插件提供（`@engine_function` 注册），`use_capability` 懒装配。

### Requirement: 函数执行实现与签名
**Reason**: 引擎函数层（M5）演化为插件框架；函数实现迁入各插件。
**Migration**: 浏览器函数迁入 `browser-plugin`；其余按能力拆入对应插件。

### Requirement: ref 确定性解析
**Reason**: ref 映射（元素引用 ↔ DOM/CSS）属浏览器插件内部实现。
**Migration**: 迁入 `browser-plugin`。

### Requirement: 页面操作绑定
**Reason**: 当前活动页绑定属浏览器插件内部。
**Migration**: 迁入 `browser-plugin`。

### Requirement: 变量写入副作用
**Reason**: 变量写入改由引擎落笔（插件只返回值），不再由引擎函数直接写变量。
**Migration**: 产出型工具声明变量目标参数，引擎拆出并写变量。

### Requirement: 错误语义
**Reason**: 分发与错误处理由插件框架统一。
**Migration**: 迁入 `plugin-system` 的「统一分发」。

### Requirement: HTTP 两种形态
**Reason**: HTTP 能力属浏览器插件。
**Migration**: 迁入 `browser-plugin`。

### Requirement: semantic_graph 函数
**Reason**: 语义图属浏览器插件。
**Migration**: 迁入 `browser-plugin`。
