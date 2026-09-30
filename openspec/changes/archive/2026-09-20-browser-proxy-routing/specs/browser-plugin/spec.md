## ADDED Requirements

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