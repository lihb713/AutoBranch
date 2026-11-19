## Decisions

### D1: ForEach 为运行期节点
解析保留 `ForEachNode`（不展开为固定次数 Repeat）；variables 支持列表/JSON 数组字符串，非列表值为标量。列表变量长度必须一致；无列表时循环 1 次，空列表循环 0 次。

### D2: 帧层级与调用栈
- Ref 帧 `parent=root`（变量隔离），ForEach 子帧 `parent=当前行为树帧`（可向上读取）。
- `SchemaSpace._call_stack` 记录调用方，`exit_frame` 从栈恢复，不依赖 `parent`。
- 保留 `config_parent`：Ref 配置仍按调用链继承，避免变量隔离破坏配置继承。

### D3: 子帧复用与结果回写
ForEach 使用一个临时子帧跨轮复用，成功轮把 body 写入的非 item 变量回写父帧。这样 `transform.append` / `dict_set` 能在循环中累积结果；item 变量循环结束随子帧移除。

### D4: 失败策略
`continue`：恢复进入本轮前的 failure_reason，跳过继续；`abort`：保留失败原因并立即返回 FAILURE。
