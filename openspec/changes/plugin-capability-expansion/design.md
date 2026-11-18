## Context

插件框架已支持用户可见函数、JSON Schema 参数与多返回值；FunctionCall 当前只按 required 参数逐个求值，导致可选参数（如 timeout、op、interactive）无法在确定性节点使用。SSH 现有实现使用 `exec_command(...).read()`，无法流式/交互。

## Decisions

### D1: 新 transform 插件而非扩展 vars

`vars.set` 的语义是“原样写入变量”，不适合承载路径/字符串/正则；新增独立 `transform` 插件，纯函数、无副作用，函数全名 `transform.*`。

### D2: FunctionCall 位置参数 + 命名参数

- 保留 `args` 位置参数；新增 `kwargs` 映射（参数名 → 值）。
- 校验：位置参数不超过参数总数；`kwargs` 不得包含未知/重复参数；required 参数必须由位置参数或 kwargs 提供。
- 运行时：位置参数按 `properties` 顺序映射，kwargs 按名称覆盖/补充；值支持字符串表达式、字面量、嵌套 dict/list。
- 兼容：旧 `args` 树继续工作；没有 `properties` 的旧函数按 required 集合校验。

### D3: SSH 流式与非交互完成判定

- 非交互：循环读取 `recv_ready`/`recv_stderr_ready`，直到 `exit_status_ready()` 且无缓冲数据，再取 `recv_exit_status()`；总超时失败。这样能可靠判断命令结束与退出码。
- 交互：`get_pty=True`，读取到 idle_timeout 无新输出后返回当前输出与 `channel_id`；进程退出则 `exited=true`。后续 `ssh_send`/`ssh_read` 增量交互，由使用方判断结束。

### D4: 代理与跳板

- SOCKS5 通过 PySocks `create_connection` 建 socket，传给 Paramiko `connect(sock=...)`。
- 跳板：先连 jump（可经 top-level/jump.proxy 的 SOCKS5），再用 jump transport `open_channel("direct-tcpip", target)` 作为目标 `sock`；jump→target 不再使用 SOCKS5。
- 会话对象保存 target client、jump client/channel 与交互通道；关闭/release 统一释放。

## Risks

- 交互命令的“完成”无法自动判断：明确由使用方依据输出/退出状态判断。
- 非交互命令若需要 TTY 或持续等待输入会超时；需改用 interactive 模式。
- 大量输出可能占用内存；调用方应通过命令侧限制输出量（后续可加 max_output）。
