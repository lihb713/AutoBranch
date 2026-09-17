## REMOVED Requirements

### Requirement: 两阶段生成流水线
**Reason**: 语义图生成并入 `browser-plugin`，不再是独立能力。
**Migration**: 作为浏览器插件内部实现。

### Requirement: 候选元素筛选规则
**Reason**: 并入 `browser-plugin`。
**Migration**: 作为浏览器插件内部实现。

### Requirement: 语义图对象模型
**Reason**: 并入 `browser-plugin`。
**Migration**: 作为浏览器插件内部实现。

### Requirement: 三种关联边
**Reason**: 并入 `browser-plugin`。
**Migration**: 作为浏览器插件内部实现。

### Requirement: 统一语义图接口与每次完整生成
**Reason**: 语义图作为浏览器插件的 `semantic_graph` 函数。
**Migration**: 迁入 `browser-plugin`。

### Requirement: LOD 分级
**Reason**: 并入 `browser-plugin`。
**Migration**: 作为浏览器插件内部实现。

### Requirement: 层次树序列化
**Reason**: 并入 `browser-plugin`。
**Migration**: 作为浏览器插件内部实现。

### Requirement: 范围边界与失败语义
**Reason**: 并入 `browser-plugin`。
**Migration**: 作为浏览器插件内部实现。
