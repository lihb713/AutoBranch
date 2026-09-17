## Purpose

文件能力插件：提供文件读写、对比、路径操作等函数。

## ADDED Requirements

### Requirement: 文件函数

系统 SHALL 通过文件插件提供文件读取、写入、对比、路径操作等函数；函数只返回值、不写变量。文件路径 SHALL 以引擎工作目录为基址（相对路径）；读取失败（不存在 / 无权限）SHALL 返回错误结果（含原因）；单文件大小 SHALL 有上限（默认 10MB，超限返回错误）。

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
