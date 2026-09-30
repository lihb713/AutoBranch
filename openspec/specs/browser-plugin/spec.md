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

### Requirement: 浏览器证书豁免配置

系统 SHALL 支持通过配置 `ignore_https_errors` 关闭浏览器会话的 HTTPS 证书校验（默认关闭）。开启后，会话内访问证书不受信任的站点（自签名 / 私有 CA / 中间人代理）SHALL 正常打开，不报证书错误；用于内网 / 私有 CA 环境。关闭时保持默认证书校验行为不变。

#### Scenario: 默认校验证书

- **WHEN** 未开启 `ignore_https_errors`，访问证书不受信任的站点
- **THEN** 打开页面失败并报告证书类错误

#### Scenario: 开启后信任全部证书

- **WHEN** 开启 `ignore_https_errors`，访问自签名 / 私有 CA 站点
- **THEN** 页面正常打开，不报证书校验错误

### Requirement: 浏览器代理路由

浏览器插件 SHALL 支持代理路由：维护一份**代理配置文件**（插件资产，缺失则不启用路由、保持默认行为），配置 `default` 兜底模式、`profiles`（system / direct / 自定义代理 server+凭据）与 `rules`（站点模式 → 代理）。系统 SHALL 在打开页面（`open(url)`）时按 URL 匹配规则选择代理：首条命中生效，无命中走 default。不同代理 SHALL 使用**独立会话（context）**承载（页面打开时定死所属会话），同一代理的多个页面共享会话；页面引用对调用方保持不透明（不暴露所属会话）。

#### Scenario: 按规则路由到自定义代理

- **WHEN** 代理配置包含规则 `*.corp.example → 公司代理`，且 `open("http://intranet.corp.example")`
- **THEN** 页面在该代理的独立会话中打开，其请求经公司代理转发

#### Scenario: 无命中走默认

- **WHEN** URL 不匹配任何规则
- **THEN** 页面按 `default` 指定的模式（system / direct / 具名 profile）打开

#### Scenario: 无配置文件保持默认

- **WHEN** 浏览器插件目录无代理配置文件
- **THEN** 路由不启用，打开页面行为与现状完全一致（跟随系统代理）

#### Scenario: 同一代理多页面共享会话

- **WHEN** 多个页面匹配同一代理
- **THEN** 它们在同一个会话（context）中打开，共享 cookie 与代理
