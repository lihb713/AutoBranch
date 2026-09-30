# browser-proxy-routing 设计

## Context

现状：`BrowserDriver.start` 启动一个浏览器 + 单个 context，`open` 在该 context 里 `new_page()`；无任何代理设置 → Chromium 跟随系统代理（无 `--no-proxy-server`，见 Q3 核实结论）。Playwright 的 proxy 是 **context 级**（`new_context(proxy=...)`），页面打开后代理定死，无法 per-request 切换。

目标：代理决策从行为树描述中移除，改为插件内配置文件 + 按 URL 路由；本期无前端 CRUD。

## Goals / Non-Goals

**Goals:**
- 浏览器插件内代理路由：配置文件（SwitchyOmega 式）+ `ProxyRouter.resolve(url)` + 驱动 context-per-mode 懒建。
- 系统代理 / 直连 / 自定义代理三种模式，页面打开时按规则定死。

**Non-Goals:**
- 前端/DB/API 的代理配置 CRUD（本期仅改配置文件）。
- per-request 代理切换（Playwright 标准能力只到 context 级）。
- LLM 传输 / `http_request` 的代理联动。

## Decisions

### D1. 代理配置文件（插件资产）

`autobranch/plugins/browser/proxy.config.json`（默认路径 = `os.path.dirname(proxy.__file__)`）；不存在/非法 → 不启用路由（现状）。格式：

```json
{
  "default": "system",
  "profiles": {
    "直连":    { "mode": "direct" },
    "公司代理": { "server": "http://proxy.corp:8080", "username": "u", "password": "p" }
  },
  "rules": [
    { "pattern": "*.corp.example", "proxy": "公司代理" },
    { "pattern": "127.0.0.1",      "proxy": "直连" }
  ]
}
```

- profile 三种：`{mode:"system"}`（默认，不传 proxy）、`{mode:"direct"}`（直连）、`{server, username?, password?}`（自定义）。
- 随附 `proxy.config.example.json` 示例；真实 `proxy.config.json` 不入库（运维本地创建）。

### D2. 插件路由模块 `proxy.py`

- `load_proxy_config(path=None) -> dict | None`：加载并做基本校验（缺失/非法返回 None）。
- `class ProxyRouter`：
  - `resolve(url) -> profile`：`urlparse` 取 host；按序匹配 `rules`（首条命中）→ 无命中用 `default`。
  - 匹配：`*` 全部；`*.x` 匹配 host==x 或 `.x` 后缀；`x` 精确匹配 host。
  - 返回规范化 profile dict（`{"mode":"system"}` / `{"mode":"direct"}` / `{server,...}`）。
- 纯函数、独立单测（多种 pattern 与优先级）。

### D3. 驱动 context-per-mode（懒建）

- `start(config, *, proxy_config=None)`：`proxy_config` 为 dict/路径/None；None 时读插件目录默认文件；无配置 → `router=None`（现状）。只 `launch` 浏览器，**不建 context**。
- `_ensure_context(proxy_key) -> context`：按需 `new_context(...)` 并缓存于 `_contexts[proxy_key]`。
  - proxy_key = `"system"` → `new_context()`（现状）；`"custom"` → `new_context(proxy={server,username,password})`。
  - **direct 实测结论**：Playwright **不支持 `proxy.server="direct://"`**（实测报 `ERR_PROXY_CONNECTION_FAILED`，把 "direct://" 当真实代理主机）。故 direct 模式经**独立浏览器进程**（懒启动 `launch(args=["--no-proxy-server"])`）承载，其 context 不带 proxy 即强制直连；system/custom 共用一个默认浏览器。代价：用到 direct 时多一个浏览器进程。
- `open(url)`：`profile = router.resolve(url)`（无 router → system）→ key → `_ensure_context` → `new_page()` → 记录 `_page_ctx[ref_id]=ctx`、`_active_id`。
- `page(ref)` / `PageHandle`：仅依赖 `_pages[ref_id]` 取页签，不感知 context；`_page_ctx` 供 `stop`/`_pump_events` 与将来报告用。
- `stop()`：关闭全部 context + 浏览器（幂等）。
- `running`：`self._browser is not None`。

### D4. 页面引用与 context 归属

- `PageRef{page_id, url}` 对调用方不透明（不暴露 context）。
- 同一 URL 在不同代理下各开一页 → 两个独立 ref_id（驱动全局递增），互不冲突。
- 页面内跳转到其他域仍留在原 context（代理打开时定死）。

## Risks / Trade-offs

- **direct 依赖独立浏览器进程**：Playwright 不支持 context 级直连（`direct://` 实测失败），用到 direct 模式会多启动一个 `--no-proxy-server` 浏览器（内存开销）。只在规则/默认命中 direct 时才懒启动。
- **代理粒度**：context 级（页面打开定死、共享 cookie），非 per-request——SwitchyOmega 可 per-request，Playwright 做不到；本期接受。
- **回环地址绕过**：Playwright 设置代理时强制 `<-loopback>` 绕过，`127.0.0.1`/localhost 永远不会走代理（集成测试需用非回环 IP 验证）。
- **配置只读**：改配置需下一次 run 生效（懒加载在 `start` 时读一次）；本期不做热加载。

## Migration Plan

无数据迁移；配置文件缺失 = 现状。`proxy.config.json` 加入 `.gitignore`（运维本地创建）。

## Open Questions

- 无阻塞项。热加载（运行中改配置生效）、前端 CRUD、LLM/http_request 代理联动留待后续。