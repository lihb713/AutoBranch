# 前端组件与状态管理规范

> 适用范围：M9a 前端（React 18 + TypeScript + Vite）。契约依据 `docs/specs/M9a-frontend-ui.md`（行为树编辑器、执行报告页轮询）。

## 1. 技术栈与目录约定

```
webops/frontend/
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

## 6. 样式约定

- 使用 CSS Modules 或 styled 方案均可，但**一个组件一个样式来源**，禁止散落的全局 class。
- 颜色 / 间距 / 字号定义为设计 token（`src/styles/tokens.css`），不用魔法数字。
- 状态色统一：SUCCESS 绿、FAILURE 红、RUNNING 蓝（执行报告节点着色）。

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