## Decisions

### D1: 目录独立表 + 路径为唯一标识

新增 `plugin_file_directories(path unique)`；`plugin_file_records.path` 存 POSIX 相对路径。空路径表示根目录（不建记录）。路径归一化拒绝 `..`。

### D2: 目录重命名级联更新

移动物理目录后，更新目录表与文件表中 `old/` 前缀的路径；拒绝移动到自身子目录、目标冲突。

### D3: 上传/下载按路径

- 上传 API 接受 `path` 表单字段；为空用原文件名。
- `GET /download?path=`：文件直接返回，目录即时生成 ZIP。
- 目录上传由前端逐文件上传并保留 `webkitRelativePath`。

### D4: 插件间共享平台文件

新增 `plugins/file/store.py`：通过服务端 DB 会话与 FileService 读写平台文件。SSH/浏览器运行期调用，不复制平台实现。

### D5: SSH 文件传输

- 直连：Paramiko SFTP `putfo`/`getfo`，远程父目录 `mkdir -p`。
- 跳板 shell：`base64 -d > path <<'EOF'` 上传；`base64 < path` 下载，复用 shell 标记命令执行。

### D6: ANSI 过滤

SSH 输出统一经 `strip_ansi` 去除 CSI/OSC 转义，避免颜色控制码污染命令结果与交互输出。
