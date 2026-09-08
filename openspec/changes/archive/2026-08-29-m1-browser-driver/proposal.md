## Why

WebOps 需要在真实浏览器中执行行为树里的页面操作、数据提取与 HTTP 请求，但目前代码库中没有任何浏览器驱动实现。依据 `docs/contract.md` §5.8（引擎函数集与 HTTP 接口）、§5.9（会话生命周期）、§5.10（页面变量机制）、§8（DOM 爬取）与 `docs/specs/M1-browser-driver.md`，浏览器驱动是 M4（语义图生成）与 M5（引擎函数层）共同依赖的地基模块（模块地图阶段1、无依赖），现在落地它可为后续模块打通真实的浏览器能力链路。

## What Changes

- 新增基于 Playwright 封装的浏览器驱动模块，作为 WebOps 唯一接触真实浏览器的组件
- 新增 context 会话管理：每次 run 创建全新 context（无历史 cookie/登录态），全流程共享、不持久化，stop 时完整释放（契约 §5.9）
- 新增页面管理：open 打开页面并返回页面引用（PageRef），按引用取回页面句柄，多页并存、操作作用于指定页（契约 §5.10）
- 新增页面操作函数：open/click/type/select/check/uncheck/scroll/wait（契约 §5.8.1）
- 新增文件函数：download/upload（契约 §5.8.1）
- 新增 HTTP 监听（形态A）：clear_requests 清理记录 / get_response 按 method+url 模式匹配页面已发生请求的响应（契约 §5.8.2）
- 新增独立请求 http_request（形态B）：不经页面的独立 HTTP 请求，认证信息由流程变量显式提供、不从页面会话自动提取（契约 §5.8.2）
- 新增截图能力：保存当前页面状态为 PNG 并返回路径（契约 §5.8.3）
- 新增 DOM 原始爬取（DomProbe.crawl）供 M4 语义图程序化阶段使用：节点树、role、可见性、包围盒、程序化值，支持 LOD 参数（契约 §8.3）
- 新增操作结果与错误语义：OpResult 携带 ok/error/detail，程序侧失败（元素不存在/网络超时等）返回可分类错误码，致命错误（浏览器崩溃/网络断开）抛出 FatalBrowserError 终止流程（契约 §9.4）
- 测试策略：真实浏览器集成测试（本地测试网页 fixture）、多页/多标签、HTTP 监听、模块独立测试

## Capabilities

### New Capabilities
- `browser-driver`: 提供 WebOps 唯一接触真实浏览器的底层能力——context 会话生命周期与页面引用管理、页面操作与文件函数、HTTP 监听与独立请求、截图、DOM 原始爬取，以及操作结果与错误语义的数据契约

### Modified Capabilities
<!-- 无既有 capability 的需求发生变更 -->

## Impact

- **新增代码**：浏览器驱动模块目录下的会话管理、页面句柄、HTTP 记录器、DOM 爬取、数据契约与错误类型（对应 `docs/specs/M1-browser-driver.md` 第 5 章接口契约）
- **被依赖方**：M4（语义图生成 DOM 爬取）、M5（引擎函数层操作执行）、M8（报告机制截图）；页面引用与页面的绑定经 M5 间接被 M3 使用
- **外部依赖**：Playwright（Python）及其浏览器二进制；测试需本地静态测试网页 fixture
- **测试影响**：真实浏览器集成测试需在独立 conda 环境内安装 Playwright 与浏览器；模块不依赖 LLM 与行为树，可独立运行全部测试