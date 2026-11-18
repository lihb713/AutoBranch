# file-plugin Specification

## Purpose

文件能力插件：为行为树叶子与 FunctionCall 节点提供确定性文件操作（读 / 写 / 对比 / 路径处理），供文件类自动化任务使用。

## Requirements
### Requirement: 文件函数

系统 SHALL 通过文件插件提供文件读取、写入、对比、路径操作等函数；函数只返回值、不写变量。文件路径 SHALL 限制在文件管理根目录 `autobranch/plugins/file/data/` 下（相对路径，禁止绝对路径与 `..` 越界）；读取失败（不存在 / 无权限）SHALL 返回错误结果（含原因）；单文件大小 SHALL 有上限（默认 10MB，超限返回错误）。

#### Scenario: 读取文件
- **WHEN** 调用 `read(path='data/a.txt')` 且该文件内容为 `x`
- **THEN** 返回文件内容 `x`

#### Scenario: 读取失败返回错误
- **WHEN** 调用 `read` 的文件不存在或无权限
- **THEN** 返回错误结果（含原因）

#### Scenario: 写入文件
- **WHEN** 调用文件写入函数
- **THEN** 写入内容并返回执行结果

#### Scenario: 文件对比
- **WHEN** 调用文件对比函数
- **THEN** 返回差异结果

#### Scenario: 路径越界
- **WHEN** 调用 `read` 传入绝对路径或 `../outside`
- **THEN** 返回失败结果，不能访问文件管理根目录之外

#### Scenario: MD5
- **WHEN** 调用 `md5(path)` 或查看文件列表
- **THEN** 返回/展示文件 MD5

### Requirement: 文件插件模块化

`file` 插件 SHALL 提供文件管理 API（列表/上传/详情/下载/删除）、`plugin_file_records` 表、`autobranch/plugins/file/data/` 存储、`max_file_size` 配置、前端清单 `{route:/file,label:文件管理,component:FileManager}`。超限上传 MUST 返回 413。


### Requirement: 目录化文件管理平台

文件平台 SHALL 支持目录与 POSIX 相对路径（如 `reports/2026/a.txt`）。系统 SHALL 提供目录 CRUD、目录重命名（同步更新后代文件路径）、递归删除、按路径上传/下载与目录 ZIP 下载。前端 SHALL 支持目录导航、上传文件/目录、下载文件/目录。单文件大小上限 SHALL 可配置。

#### Scenario: 创建目录并上传
- **WHEN** 创建目录 `reports` 并上传文件到 `reports/a.txt`
- **THEN** 文件列表/目录列表按路径展示该文件

#### Scenario: 重命名目录
- **WHEN** 将 `reports` 重命名为 `archive`
- **THEN** 其中文件的路径同步变为 `archive/...`

#### Scenario: 下载目录
- **WHEN** 请求下载目录
- **THEN** 返回包含该目录全部内容的 ZIP
