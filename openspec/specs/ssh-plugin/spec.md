# ssh-plugin Specification

## Purpose

SSH 能力插件：创建 / 关闭远程会话、在远程主机执行命令等；会话对象作为泛型对象值在变量中传递。

## Requirements
### Requirement: SSH 会话与远程执行

系统 SHALL 通过 SSH 插件提供：创建会话、关闭会话、在远程主机执行命令等函数；会话对象 SHALL 作为泛型对象值存储与传递，函数只返回值、不写变量。会话创建 SHALL 支持端口、密码/密钥、连接超时、SOCKS5 代理与 SSH 跳板机；有跳板机时 proxy 仅用于连接跳板机；跳板机到目标机 SHALL 在跳板机 PTY shell 中执行 `ssh` 命令（不使用 `direct-tcpip`，以兼容禁止通道转发的环境），目标认证 SHALL 使用密码 `pwd`。

`ssh_exec` 默认 SHALL 以非交互模式流式读取 stdout/stderr，等待 SSH 通道 exit-status 后返回 stdout/stderr/exit_code，非零退出码作为失败；交互模式（`interactive=true`）SHALL 使用 PTY，idle 超时后返回当前输出与 `channel_id`，并通过 `ssh_send`/`ssh_read`/`ssh_close_channel` 持续交互。

#### Scenario: 创建会话并执行命令
- **WHEN** 调用 `create_session(host='192.168.1.10', port=22, user='root', pwd='...')` 后调用 `ssh_exec(session, 'echo hi')`
- **THEN** 返回命令输出 `hi`

#### Scenario: 命令失败返回失败结果
- **WHEN** `ssh_exec` 执行的命令退出码非零或超时
- **THEN** 返回失败结果（含命令与退出码 / 超时原因）

#### Scenario: 显式关闭会话
- **WHEN** 调用 `close_session(session)`
- **THEN** 会话关闭

#### Scenario: 会话作为变量传递
- **WHEN** 创建会话返回会话对象
- **THEN** 该对象可存入变量、经 args / returns 传递给后续函数

#### Scenario: SOCKS5 代理
- **WHEN** `create_session` 传入 `proxy={host, port}`
- **THEN** SSH 连接经 SOCKS5 代理建立

#### Scenario: SSH 跳板机
- **WHEN** `create_session` 传入 `jump={host, user, ...}`
- **THEN** 先连接跳板机，在跳板机 shell 中执行 `ssh` 登录目标机，后续命令通过该 PTY shell 执行

#### Scenario: 交互式命令
- **WHEN** `ssh_exec(interactive=true)` 启动需要输入的命令
- **THEN** 返回当前输出与 channel_id；后续 `ssh_send` 写入输入、`ssh_read` 读取增量输出


### Requirement: SSH 文件平台互通与输出清洗

SSH 插件 SHALL 提供 `upload_file(session, file_path, remote_path)` 与 `download_file(session, remote_path, file_path?)`，在文件管理平台与远程主机之间传输文件。直连模式 SHALL 使用 SFTP；跳板 shell 模式 SHALL 使用 base64。SSH 命令/交互输出 SHALL 过滤 ANSI 转义序列。

#### Scenario: 从平台上传
- **WHEN** 调用 `upload_file` 指定平台路径与远程路径
- **THEN** 平台文件内容上传到远程文件

#### Scenario: 下载到平台
- **WHEN** 调用 `download_file` 指定远程路径与平台路径
- **THEN** 远程文件写入文件管理平台

#### Scenario: ANSI 输出
- **WHEN** 远程命令输出包含颜色转义序列
- **THEN** 返回结果中不包含 ANSI 控制码
