# AutoBranch 前端设计系统

> 适用于 `autobranch/frontend/`。目标：保持现有页面结构与业务逻辑不变，用统一 token/组件类规范视觉呈现。

## 1. 设计令牌

唯一定义位置：`src/styles/tokens.css`。禁止在业务组件中硬编码颜色/间距/圆角/阴影（语义化的树节点类型颜色除外）。

### 间距

4px 基准：`--space-1` 4、`--space-2` 8、`--space-3` 12、`--space-4` 16、`--space-5` 24、`--space-6` 32、`--space-7` 40、`--space-8` 48。

### 色彩

| Token | 用途 | 默认值 |
|---|---|---|
| `--color-primary` | 主按钮/链接/焦点 | `#2563eb` |
| `--color-primary-hover` | 主色 hover | `#1d4ed8` |
| `--color-primary-soft` | 主色浅背景/焦点环 | `#eff6ff` |
| `--color-text` | 主文本 | `#1f2937` |
| `--color-muted` | 次要文本 | `#6b7280` |
| `--color-bg` | 页面背景 | `#f9fafb` |
| `--color-surface` | 卡片/弹窗背景 | `#ffffff` |
| `--color-bg-muted` | 表头/弱背景 | `#f3f4f6` |
| `--color-border` | 默认边框 | `#e5e7eb` |
| `--color-success` / `--color-success-bg` | 成功 | `#15803d` / `#f0fdf4` |
| `--color-failure` / `--color-failure-bg` | 失败 | `#b91c1c` / `#fef2f2` |

### 排版

字体族 `--font-family`，等宽 `--font-family-mono`；字号 `--font-size-xs`(12)、`--font-size-base/md`(14)、`--font-size-16`(16)、`--font-size-lg`(18)、`--font-size-xl`(24)；行高 `--line-height-tight/normal/relaxed`。

### 圆角 / 阴影 / 控件

- 圆角：`--radius-sm` 4、`--radius`/`--radius-md` 8、`--radius-lg` 12、`--radius-pill` 999
- 阴影：`--shadow-sm` / `--shadow-md` / `--shadow-lg`
- 控件：`--control-height` 36、`--control-height-lg` 40、`--border-width` 1

## 2. 组件规范

统一样式位置：`src/styles/design-system.css`（在 `index.css` 之后加载，作为最终视觉覆盖）。

- **页面**：`.page` + `.page-header` + `.page-title`；标题 24px，页头底部 16px 间距与 1px 分隔线。
- **按钮**：统一使用 `components/Button.tsx` 的 `.btn`；变体 `primary` / `ghost` / `danger`。高度 36px、圆角 8px、hover/active/focus-visible 状态统一。
- **表单**：`.text-field` / `.text-field__input`；输入框高度 36px、圆角 8px，focus 使用主色边框 + 3px 浅色焦点环。弹窗内表单使用同一 token。
- **表格**：`.tree-table`；表头 `--color-bg-muted`、12px 次要文本、行高由 `--space-3` 控制、行 hover 弱背景、最后一行无底边框。
- **卡片/面板**：`.run-meta` / `.report-node` / `.plugin-card` / `.outputs-section` 等统一 surface + border + radius-md + shadow-sm。
- **弹窗**：`.modal-overlay` + `.modal-panel`；居中、遮罩、圆角 12px、shadow-lg。调度编辑/执行记录、执行入参对话框均使用该组合。
- **导航**：`.global-nav` / `.global-nav__tab`，激活态使用 surface + border，不再使用独立配色。
- **状态**：`StatusBadge` / `source-badge` / `schedule-status` 统一 pill 形状与语义色。

## 3. 开发约束

1. 新样式优先复用 token 与设计系统类，不写 magic number。
2. 修改页面布局时不得改变业务逻辑、状态管理或 API 请求。
3. 新增 UI 组件应复用 `Button` / `TextField` / `EmptyState` / `ErrorMessage` 等通用组件；确实需要新组件时，先在设计系统文档补充其类名与 token 用法。
4. 主题色/间距调整只改 `tokens.css`，不在业务组件覆盖。
5. 改动后必须运行前端 `npm run typecheck && npm run lint && npm test && npm run build`，涉及核心链路时补充 Playwright E2E。
