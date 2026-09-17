## Purpose

SSH 能力插件：创建 / 关闭远程会话、在远程主机执行命令等；会话对象作为泛型对象值在变量中传递。

## ADDED Requirements

### Requirement: SSH 会话与远程执行

系统 SHALL 通过 SSH 插件提供：创建会话、关闭会话、在远程主机执行命令等函数；会话对象 SHALL 作为泛型对象值存储与传递（与页面对象一致），函数只返回值、不写变量。会话创建 SHALL 支持端口、认证方式（密码 / 密钥）、连接超时；`ssh_exec` SHALL 支持命令超时；命令非零退出码 SHALL 作为失败结果返回。

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
