## Why

文件管理平台目前只有扁平文件列表，无法按目录分类；SSH/浏览器也无法直接使用平台文件，只能在本地路径与远程/页面之间操作。需要增加目录化文件平台与插件间文件互通。

## What Changes

- 文件平台增加目录表与 POSIX 相对路径（如 `reports/2026/a.txt`）。
- 文件插件增加目录 CRUD、目录重命名（同步更新后代文件路径）、按路径上传/下载、目录 ZIP 下载。
- 前端文件管理支持目录导航、新建/改名/递归删除目录、上传目录（保留相对路径）、下载文件/目录。
- SSH 增加 `upload_file` / `download_file`：从文件平台取文件上传、下载到文件平台；直连用 SFTP，跳板 shell 用 base64。
- 浏览器增加 `upload_from_platform` / `download_to_platform`：页面文件控件与平台文件互通。
- SSH 输出统一过滤 ANSI 转义序列。

## Impact

- 后端：`plugins/file`（模型/服务/API/函数/store）、`plugins/ssh`、`plugins/browser`。
- 前端：文件管理页、file API。
- 测试：文件目录/路径 API、SSH/浏览器联动、ANSI、Frontend 组件、E2E 文件管理。
- 文档 specs/OpenSpec/user-guide。
