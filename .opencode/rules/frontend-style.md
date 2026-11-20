# 前端组件与状态管理规范

> 适用范围：M9a 前端（React 18 + TypeScript + Vite）。契约依据 `docs/specs/M9a-frontend-ui.md`（行为树编辑器、执行报告页轮询）。
> 视觉规范统一遵循本文件 §5 设计系统：颜色/间距/字号/圆角/阴影只能使用 `src/styles/tokens.css` 中的 token。

## 1. 技术栈与目录约定

```
autobranch/frontend/
├── src/
│   ├── api/                  # 后端 API 客户端（fetch 封装 + 类型）
│   ├── components/           # 通用 UI 组件（无业务状态）
│   ├── features/             # 业务模块：tree-editor / runs / reports
│   │   ├── tree-editor/
│   │   │   ├── TreeEditorPage.tsx
│   │   │   ├── NodePalette.tsx
│   │   │   ├── useBehaviorTree.ts      # 模块内状态逻辑（hooks）
│   │   │   └── TreeEditorPage.test.tsx
│   ├── hooks/                # 跨模块复用 hooks（如 usePolling）
│   ├── types/                # 领域类型（与后端 schema 对应）
│   └── main.tsx
```

- 组件分两类：`components/` 为**通用无业务状态**组件；`features/*/` 为**页面级业务组件**。
- 文件命名：组件 `PascalCase.tsx`，hook `useCamelCase.ts`，测试同目录 `*.test.tsx`。

## 2. 组件书写规则

### 2.0 视觉样式使用设计系统

- 页面、按钮、表单、表格、卡片、弹窗、导航统一样式位于 `src/styles/design-system.css`，不要另起一套视觉语言。
- 业务组件不得硬编码颜色（语义化节点类型色除外）、间距、圆角、阴影；统一使用 `--space-*` / `--color-*` / `--radius-*` / `--shadow-*`。
- 新增弹窗使用 `.modal-overlay` + `.modal-panel`；新增表格使用 `.tree-table`；新增操作按钮优先使用 `components/Button.tsx`。

### 2.1 函数组件 + TypeScript props

- 统一函数组件，props 用类型注解显式声明。不用 `any`、不写 `defaultProps`。

```tsx
// ✅
type ButtonProps = {
  label: string;
  onClick: () => void;
  variant?: "primary" | "ghost";
  disabled?: boolean;
};

function Button({ label, onClick, variant = "primary", disabled = false }: ButtonProps) {
  return (
    <button type="button" className={`btn btn-${variant}`} onClick={onClick} disabled={disabled}>
      {label}
    </button>
  );
}

// ❌
function Button(props: any) { ... }
```

### 2.2 props 不可变、单向数据流

- 组件不直接修改传入对象；状态更新一律通过回调或状态提升。

```tsx
// ✅ 受控组件：父组件持状态，子组件通过回调上报
function TreeNameInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <input value={value} onChange={(e) => onChange(e.target.value)} />;
}

// ❌ 子组件直接 setState 父级数组
```

### 2.3 渲染列表必带 key

```tsx
{treeList.map((tree) => (
  <TreeRow key={tree.id} tree={tree} onEdit={() => onEdit(tree.id)} />
))}
// key 用稳定 id，不用数组 index（删除/重排时会错位）
```

## 3. 状态管理

### 3.1 分层决策

| 状态类型 | 管理方式 |
|---|---|
| 组件内 UI 状态（表单、折叠、弹窗） | `useState` |
| 模块内共享状态（编辑器节点树） | `useReducer` 或 hooks 组合 |
| 跨页面 / 全局状态 | **Context**（此项目规模不建议引入 Redux） |

- 原则：**就近原则**——状态放尽量靠近使用它的组件；页面级状态放 feature hook，不要全塞全局。
- 派生状态用 `useMemo`，不额外开 `useState` 同步。

```tsx
// ✅ 派生值不重复存 state
const { nodes } = useBehaviorTree();
const leafCount = useMemo(() => nodes.filter((n) => n.kind === "Action" || n.kind === "Condition").length, [nodes]);

// ❌ const [leafCount, setLeafCount] = useState(0); useEffect(() => setLeafCount(...), [nodes]);
```

### 3.2 reducer 用于复合更新（编辑器节点树）

```tsx
type TreeAction =
  | { type: "addNode"; parentId: string; node: TreeNode }
  | { type: "updateNode"; id: string; patch: Partial<TreeNode> }
  | { type: "removeNode"; id: string }
  | { type: "moveNode"; id: string; targetParentId: string };

function treeReducer(state: TreeNode[], action: TreeAction): TreeNode[] {
  switch (action.type) {
    case "addNode":
      return insertNode(state, action.parentId, action.node);
    case "updateNode":
      return mapNode(state, action.id, (n) => ({ ...n, ...action.patch }));
    default:
      return state;
  }
}
```

### 3.3 轮询 hook（执行报告页）

契约 §12.4：前端每秒轮询执行状态。抽成通用 hook，卸载时清理：

```ts
// src/hooks/usePolling.ts
import { useEffect, useRef, useState } from "react";

export function usePolling<T>(
  fetcher: () => Promise<T>,
  shouldStop: (data: T) => boolean,
  intervalMs = 1000,
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const next = await fetcher();
        if (cancelled) return;
        setData(next);
        if (shouldStop(next)) return; // 执行完毕，停止轮询
        timer = setTimeout(tick, intervalMs);
      } catch (err) {
        if (!cancelled) setError(err as Error);
      }
    };

    void tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [fetcher, shouldStop, intervalMs]);

  return { data, error };
}
```

```tsx
// 用法：轮询 /api/runs/{id}/state，finished 后停止
const { data, error } = usePolling(
  () => api.getRunState(runId),
  (state) => state.finished,
);
```

## 4. API 访问层

### 4.1 集中封装，组件不直接 fetch

```ts
// src/api/trees.ts
import type { TreeCreate, TreeOut } from "../types/tree";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(await extractError(res));
  }
  return res.json() as Promise<T>;
}

export const api = {
  listTrees: () => request<TreeOut[]>("/trees"),
  getTree: (id: number) => request<TreeOut>(`/trees/${id}`),
  saveTree: (payload: TreeCreate) =>
    request<TreeOut>("/trees", { method: "POST", body: JSON.stringify(payload) }),
  runTree: (id: number) => request<{ run_id: string }>(`/trees/${id}/run`, { method: "POST" }),
  getRunState: (runId: string) => request<RunState>(`/runs/${runId}/state`),
};
```

### 4.2 类型与后端 schema 一一对应

- `types/` 下类型命名与后端 Pydantic 输出一致（snake_case），不手写重复转换。

```ts
// src/types/tree.ts —— 对应后端 TreeOut
export type TreeOut = {
  id: number;
  name: string;
  created_at: string;
  updated_at: string;
};

export type RunState = {
  run_id: string;
  progress: number;
  current_node: NodeInfo | null;
  completed: NodeReport[];
  finished: boolean;
};
```

## 5. 行为树编辑器（复合节点视图）

- 用户始终看到**含复合节点**的行为树（Step/Branch/LoopUntil/IfThenElse/Retry/Sequence/ref），引擎基础节点对用户不可见（契约 §12.5）。
- 编辑器产出 yaml 文本交由后端保存；**不在前端展开复合节点**。

```tsx
// 节点类型定义（与 §4.3 复合节点对应）
export type CompositeNodeType =
  | "Step"
  | "Branch"
  | "LoopUntil"
  | "IfThenElse"
  | "Retry"
  | "Sequence"
  | "ref";
```

## 6. 设计系统

> 适用于 `autobranch/frontend/`。目标：保持现有页面结构与业务逻辑不变，用统一 token/组件类规范视觉呈现。

### 6.1 设计令牌

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

### 6.2 原子组件规范

统一样式位置：`src/styles/design-system.css`（在 `index.css` 之后加载，作为最终视觉覆盖）。

- **页面**：`.page` + `.page-header` + `.page-title`；标题 24px，页头底部 16px 间距与 1px 分隔线。
- **按钮**：统一使用 `components/Button.tsx` 的 `.btn`；变体 `primary` / `ghost` / `danger`，尺寸 `sm/md/lg`。高度 32/36/40px、圆角 8px，hover/active/focus-visible/disabled 状态统一。
- **表单**：`TextField` / `TextAreaField` / `SelectField` / `CheckboxField`；统一高度 36px、圆角 8px、focus 主色边框 + 3px 浅色焦点环。原生 textarea 使用同一 `--control-height` 与 padding 规则。
- **徽标**：`StatusBadge` / `Badge`（neutral/primary/success/failure/warning）统一 pill 圆角、12px 字号、语义色。
- **表格**：`.tree-table`；表头 `--color-bg-muted`、12px 次要文本、行高由 `--space-3` 控制、行 hover 弱背景、最后一行无底边框。
- **卡片/面板**：`.run-meta` / `.report-node` / `.plugin-card` / `.outputs-section` 等统一 surface + border + radius-md + shadow-sm。
- **弹窗**：`.modal-overlay` + `.modal-panel`；居中、遮罩、圆角 12px、shadow-lg。调度编辑/执行记录、执行入参对话框均使用该组合。
- **导航**：`.global-nav` / `.global-nav__tab`，激活态使用 surface + border，不再使用独立配色。
- **状态**：`StatusBadge` / `source-badge` / `schedule-status` 统一 pill 形状与语义色。

### 6.3 布局与开发约束

1. 新样式优先复用 token 与设计系统类，不写 magic number。
2. 修改页面布局时不得改变业务逻辑、状态管理或 API 请求。
3. 新增 UI 组件应复用 `Button` / `TextField` / `EmptyState` / `ErrorMessage` 等通用组件；确实需要新组件时，先在本文件 §6 设计系统补充其类名与 token 用法。
4. 主题色/间距调整只改 `tokens.css`，不在业务组件覆盖。
5. 改动后必须运行前端 `npm run typecheck && npm run lint && npm test && npm run build`，涉及核心链路时补充 Playwright E2E。

## 7. Do's & Don'ts 速查

| Do ✅ | Don't ❌ |
|---|---|
| 函数组件 + 显式 props 类型 | 写 `props: any`、类组件 |
| 受控组件单向数据流 | 子组件直接改父级状态 |
| 就近管理状态，派生值 useMemo | 全局 state 塞一切 / 用 useEffect 同步 state |
| 列表 key 用稳定 id | key 用数组 index |
| API 调用集中在 `src/api/` | 组件内散落 fetch |
| 轮询用可清理的 hook | 组件里裸写 setInterval 不清理 |
| 类型与后端 schema 对齐 | 前后端字段各命名一套 |
| 编辑器产出复合节点 yaml | 前端自行展开基础节点 |
| 视觉使用 `src/styles/tokens.css` 的 token | 硬编码颜色/间距/px 魔法数字 |
| 表单优先使用 TextField/TextAreaField/SelectField/CheckboxField | 每个页面各写一套 input/select 样式 |
| 页面/表格/弹窗复用设计系统 class | 同一页面混用多套按钮/表格/弹窗风格 |
| 同类操作使用同一 Button variant/size | 表格操作区混用超链接与边框按钮 |
| 表单统一 `.text-field` + 焦点环 | 输入框各自设置高度/边框/对齐 |
