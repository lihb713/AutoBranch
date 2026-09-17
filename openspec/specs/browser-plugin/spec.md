# browser-plugin Specification

## Purpose

浏览器能力插件：提供网页操作（打开 / 点击 / 输入 / 提取 / 语义图等），自包含浏览器驱动、语义图生成、元素引用映射、页面对象与截图。

## Requirements
### Requirement: 浏览器操作函数

系统 SHALL 通过浏览器插件提供网页操作函数（最小集）：`open` / `activate` / `get_url` / `click` / `type` / `select` / `check` / `uncheck` / `scroll` / `wait` / `download` / `upload` / `extract` / `semantic_graph` / `http`。函数 SHALL 只返回值（业务值 + 报告附加信息），不直接写变量。

#### Scenario: 打开页面并操作
- **WHEN** LLM 调用 `open(url)`
- **THEN** 浏览器插件打开页面并返回页面对象

#### Scenario: 提取页面元素值
- **WHEN** 调用 `extract(ref)`
- **THEN** 返回该元素的文本 / 值（不写变量）

#### Scenario: 打开失败返回错误结果
- **WHEN** `open` 因网络 / DNS / 超时失败
- **THEN** 返回错误结果（含原因）给调用方（LLM 可修正）

#### Scenario: 元素缺失返回空与提示
- **WHEN** `extract` 目标元素不存在
- **THEN** 返回空值并附缺失提示

#### Scenario: 页面失效报错
- **WHEN** `activate` 一个已关闭的页面对象
- **THEN** 返回错误结果（页面失效）

### Requirement: 语义图与截图

系统 SHALL 在 `semantic_graph`（"看页面"）时生成语义图并**强制截图**；截图 SHALL 作为插件报告附加信息写入报告，而非由编排器无条件截。

#### Scenario: 看页面时截图
- **WHEN** 调用 `semantic_graph`
- **THEN** 生成语义图并截图，截图写入报告

### Requirement: 页面对象与当前活动页

系统 SHALL 由浏览器插件维护页面对象与当前活动页；页面对象 SHALL 作为泛型对象值在变量中存储与传递，引擎核心不感知"页面"概念。

#### Scenario: 页面对象作为变量
- **WHEN** `open` 返回页面对象
- **THEN** 该对象可存入变量、经 args / returns 传递、供 `activate` 使用

#### Scenario: 打开后成为当前活动页
- **WHEN** 打开一个页面
- **THEN** 该页成为当前活动页，后续页面操作作用于它

### Requirement: 浏览器插件自包含

系统 SHALL 将浏览器驱动与语义图生成作为浏览器插件的内部实现；它们不再作为独立能力对外暴露。

#### Scenario: 仅浏览器插件使用驱动与语义图
- **WHEN** 非浏览器能力（计算 / SSH / 文件）执行
- **THEN** 不依赖浏览器驱动与语义图生成
