# browser-proxy-routing 提案

## Why

实际访问部分站点需走特定代理（系统代理 / 直连 / 自定义代理含凭据），但代理决策不应写进行为树/叶子描述（IP/端口/账号密码会污染树的可读性）。需要一种 **SwitchyOmega 式**的浏览器代理路由：浏览器插件内维护一份代理配置文件（哪些站点走哪个代理），在打开页面时按 URL 匹配并选择对应代理。本期仅支持**后台修改配置文件**，不做前端增删改查。

## What Changes

- **代理配置文件（浏览器插件资产）**：`autobranch/plugins/browser/proxy.config.json`（不存在则不启用路由，保持现状）——`default` 兜底模式 + `profiles`（system / direct / 自定义 server+凭据）+ `rules`（站点模式 → 代理，首条命中）。随附 `proxy.config.example.json` 示例。
- **插件内路由模块** `autobranch/plugins/browser/proxy.py`：`load_proxy_config()`（容错加载）+ `ProxyRouter.resolve(url) -> profile`（hostname 模式匹配，首条命中，无命中走 default）。
- **驱动接入**（driver.py）：`BrowserDriver` 懒建**每代理模式一个 context**（`system` / `direct` / 每自定义 profile）；`open(url)` → `resolve(url)` → 取/建对应 context（带对应 proxy 参数）→ 打开页面；页面引用经驱动内部 `_page_ctx` 映射到所属 context（`page_ref` 对调用方不透明）；`stop()` 关闭全部 context。
- **范围边界**：代理配置仅经**配置文件修改**生效（后台/运维直接编辑），本期**不做前端 CRUD、不做 DB/API**；`page_ref` 不暴露 context。

**BREAKING**：无（无配置文件时行为与现状完全一致）。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `browser-plugin`: 浏览器插件 SHALL 支持代理路由——按站点规则（SwitchyOmega 式配置文件）在打开页面时选择代理（system / direct / 自定义），并支持每代理模式独立会话（context）。

## Impact

- **插件内**：`autobranch/plugins/browser/proxy.py`（新）、`proxy.config.example.json`（新）、`driver/driver.py`（context-per-mode 懒建 + `_page_ctx` 映射 + `open` 路由）。
- **测试**：路由匹配单测、`direct://` 透传实测、真实浏览器集成测试（本地记录代理验证请求经代理转发）。
- **文档**：契约 §5.1/浏览器配置、M7-plugin-set / M1 相关章节、README（代理路由配置示例与说明）。

**依赖**：无。范围仅浏览器插件内，不触管理系统（无 DB/API/前端/E2E 前端链路）。