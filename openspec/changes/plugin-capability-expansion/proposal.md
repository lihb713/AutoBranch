## Why

现有插件能力偏弱：缺少通用数据提取/字符串变换，compute 只有少量算术，SSH 仅支持直连与阻塞式命令。需要增强预置插件，使行为树可以用确定性节点完成常见数据处理与远程运维。

## What Changes

- 新增 `transform` 数据提取/变换插件：路径/索引/键读取、字符串切分/拼接/搜索/替换、长度/切片、JSON、正则、通用比较、类型转换。
- 扩展 `compute`：加减乘除/整除/取模/幂/开方/绝对值/取反/四舍五入/聚合/区间/百分比/增减，`compare` 支持操作符；非法输入返回失败。
- 扩展 `ssh`：SOCKS5 代理、SSH 跳板机（jump→target 在跳板机 shell 中执行 ssh）、非交互命令流式读取并判断 exit-status、交互式 PTY 通道 `ssh_send`/`ssh_read`/`ssh_close_channel`。
- FunctionCall 支持命名参数 `kwargs`：可按参数名传可选参数（支持嵌套 dict/list），无需为靠后的参数补前置占位。
- 增加 `paramiko` / `PySocks` 依赖。

## Impact

- 插件：`autobranch/plugins/transform/`、`compute`、`ssh`。
- 核心：`parser/checks.py`、`orchestrator/traverser.py` 的可选参数校验/求值。
- 依赖：`pyproject.toml`；文档 specs/OpenSpec/user-guide。
