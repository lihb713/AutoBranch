# browser-proxy-routing 任务

## 1. 插件路由模块（proxy.py + 配置示例）

- [x] 1.1 `autobranch/plugins/browser/proxy.py`：`load_proxy_config(path)`（容错，缺失/非法返回 None）+ `ProxyRouter.resolve(url)`（hostname 匹配：`*` / `*.x` 后缀 / `x` 精确；首条命中；无命中走 default）；单测覆盖各类 pattern、优先级、default、非法配置返回 None
- [x] 1.2 `proxy.config.example.json` 示例文件 + `.gitignore` 增加 `proxy.config.json`（运维本地创建，不入库）

## 2. 驱动 context-per-mode 接入（driver.py）

- [x] 2.1 `BrowserDriver.start(config, *, proxy_config=None)`：懒加载路由配置（无配置保持现状）；只 launch 浏览器不预建 context；`_ensure_context(proxy_key)` 懒建（system / direct / 自定义）
- [x] 2.2 `open(url)` 按 `router.resolve(url)` 路由到对应 context；`_page_ctx` 记录 ref→context；`stop()` 关闭全部 context；`running` 改判浏览器存活；单测/集成测试：system 直连可用、direct 路由、自定义代理路由、同一代理多页共享 context、无配置现状兼容
- [x] 2.3 **实测 `direct://`**：`new_context(proxy={"server":"direct://"})` 是否被 Playwright 透传；不行则退化为独立浏览器（`--no-proxy-server`）

## 3. 集成/E2E 与文档

- [x] 3.1 真实浏览器集成测试：本地"记录代理"验证——配置规则 `127.0.0.1 → 自定义代理(本地记录代理)`，`open` 页面后断言请求确实经代理转发；`direct` 模式路由到失效代理仍能打开（证明直连）
- [x] 3.2 更新 `docs/contract.md` §5.1/浏览器配置、M7-plugin-set / M1 相关章节、README（代理路由配置示例与说明）
- [x] 3.3 全量验证：`pytest`、`ruff`、相关 E2E；按 AGENTS.md 提交并推送（中文提交信息）