# 页面变量机制补全设计（多页签并存与切换）

> 日期：2026-09-03
> 状态：设计稿（待用户审阅）
> 范围：M1 浏览器 / M3 schema / M5 引擎函数 / M6 叶子执行 / M8 报告 / M9a 前端（黑板）
> 关联：契约 §5.10（页面变量机制）、变量引用重构设计（get/set 语法）

## 背景与动机

契约 §5.10 设计页面变量机制："页面是命名变量、多页并存、切换由变量指定、LLM 不需要感知多标签页"。但当前实现是**简化版**，存在两个缺口：

1. **open 写死单一变量**：M5 `open(url)` 总是写入 `$this/page`（`page_var` 默认），覆盖前一次页面。无"命名页签"能力。
2. **无页签切换**：所有操作绑定"最近 open 的页"（`current_page` = 最近写入的页面变量）。无法表达"A 操作完切到 B、再回 A"。

用户场景暴露问题：行为树先访问 A 再访问 B，之后需返回 A 操作——当前每次 open 都 `new_page()` 新开，且无法切回旧页签。

**核心歧义**（用户提出）：如何区分"存页签引用"vs"存 url 字符串"、"按 url 开新页"vs"切回已有页签"——LLM 需明确判断。

## 目标

1. **类型化页面变量**：`{{set:page:name}}` 存页签引用（PageRef），`{{set:string:name}}` 存文本（url 字符串）。**blackboard 实际存储类型与标注一致**。
2. **open 支持命名页签**：`open(url, save_to)` 把新建页签存入指定变量。
3. **独立 activate 引擎函数**：把已存页签变量设为当前活动页，后续操作作用于它（多页切换）。
4. **函数意图与自然语言对齐**：LLM 看描述调用 open（开新页）或 activate（切回旧页），不混淆。

## 设计

### 1. 类型化 set 语法（扩展变量重构的 set）

变量引用重构定义了 `{{set:this/name}}`（默认文本/引擎推断）。本设计扩展**显式类型标注**：

| 语法 | 语义 | blackboard 存储类型 |
|---|---|---|
| `{{set:page:页面A}}` | 声明本动作将把页签引用存入 页面A | PageRef |
| `{{set:string:url}}` | 声明将 url 字符串存入 url | 文本（str） |
| `{{set:this/name}}`（无类型） | 引擎按动作推断（open→page，extract→string） | 推断 |

- 无类型标注时引擎推断：`open` 相关动作产出 PageRef；`extract` 产出文本。
- **标注即类型契约**：写入时 M3 强校验值类型与标注一致（如 `set:page` 却写 str → 拒绝）。

### 2. open 引擎函数扩展（保存命名页签）

```
open(url, save_to?) -> OpResult
  - 打开 url（M1 新开页签）
  - save_to 提供时：把新建页签 PageRef 写入 save_to 变量（类型 page）
  - save_to 省略时：保持当前行为（写默认活动页变量）
```

- ToolSpec：`url`（必填）+ `save_to`（可选，形如 `this/页面A`，说明"将页签引用存入该变量"）。
- LLM 从描述 `{{set:page:页面A}}` 得知应把页签存到 `this/页面A` → 调 `open(url, save_to="this/页面A")`。
- 若描述无 `set:page`，LLM 可省略 save_to（存默认活动页）。

### 3. activate 引擎函数（新增，页签切换）

```
activate(page_var) -> OpResult
  - 解析 page_var 指向的变量（必须是页面引用类型，否则报错）
  - 验证该页签仍打开（M1 按 page_ref 取回 page 对象）
  - 设为"当前活动页"，后续 click/type/semantic_graph 作用于它
```

- **只切焦点，不新建**。page_var 不存在或非页面引用 → 返回明确错误（"该变量不是页面引用，请先 open"），LLM 可据此修正。
- ToolSpec：`page_var`（必填，形如 `this/页面A`）。
- 触发词引导：LLM 看到"回到/切到/使用已打开的 X 页" → activate。

### 4. "当前活动页"语义调整

现状：`current_page` = 帧中**最近写入**的页面变量。调整后：

```
当前活动页 = 最近一次 activate 指定的页签变量；若无 activate，回退最近 open 的页签。
```

- `open(url, save_to)` 打开新页后，新页成为活动页（等同原行为）。
- `activate(page_var)` 后，活动页 = 该变量页签。
- 操作函数（click/type/semantic_graph）始终作用于当前活动页。

### 5. M1 底层（几乎无改动）

- M1 `_pages[ref_id] = page` 已保留会话内全部页签；`page(PageRef)` 可按 ref 取回任意页签句柄。
- 页签生命周期：会话结束（stop）才释放（契约 §5.9）。
- Playwright 层"切换"即引用对应 page 对象，M1 已具备。

### 6. url 字符串存储（与页签区分）

要存当前页 url 字符串（非页签）：描述用 `{{set:string:url}}` + 引擎函数取当前 url。
- 新增轻量引擎函数 `get_url(save_to)`（取当前活动页 url 存为文本）或复用 extract 语义。
- 与页签引用的区分靠：变量类型标注 + 函数不同（open→page，get_url/extract→string）。

## 涉及模块改动

| 模块 | 改动 |
|---|---|
| M2 parser | `{{set:page:...}}`/`{{set:string:...}}` 类型标注解析；set_targets 携带类型 |
| M3 schema | `set:page` 写入 PageRef 强校验；类型名含 page/string 语义映射 |
| M5 engine | `open` 加 save_to；新增 `activate(page_var)`；`get_url`；当前活动页逻辑调整 |
| M6 leaf | set_targets 类型信息注入提示词；extract 校验适配类型 |
| M6 prompts | open/activate/get_url 触发词引导；页签 vs url 意图区分说明 |
| M8 reporting | blackboard 变量含类型（PageRef 展示为页签 id+url） |
| M9a frontend | 黑板页签变量渲染优化 |

## 范围边界

- ref 块引用绑定 `$this/` 仍不在本次范围（另行设计）。
- iframe/多窗口（popup）不在范围。

## 测试

- M5：open save_to 存页签、activate 切换、activate 非页签变量报错、get_url 存文本。
- M2/M3：set:page 类型标注与强校验。
- 端到端：行为树 A→B→activate(A)→操作 A，验证切回旧页签。
- 前端：黑板展示页签变量（id+url）。

## 开放问题

- url 字符串取用的确切引擎函数形态（get_url vs extract 扩展）——实现时定，不影响核心设计。
