# 单元测试与 E2E 测试规范

> 适用范围：引擎层（Python pytest）+ 管理系统前端（Vitest / React Testing Library）+ E2E（Playwright）。契约依据各模块 spec 的「测试策略」章节。

## 1. 工具与分层

| 层级 | 工具 | 命令 |
|---|---|---|
| 引擎单元测试 | pytest | `pytest` |
| 引擎集成测试（真实浏览器） | pytest + Playwright | `pytest -m integration` |
| 前端单元测试 | Vitest + React Testing Library | `npm test` |
| E2E 测试 | Playwright | `npm run test:e2e` |

**测试金字塔**：单元测试为主（mock 外部依赖），集成/E2E 只覆盖关键链路。每个模块 spec 都定义了自己的独立性测试边界——**模块测试不依赖其依赖模块的真实实现**（M6 测 M5 用 mock、M7 测 M6/M8 用 mock）。

## 2. Python 引擎测试（pytest）

### 2.1 目录与命名

```
autobranch/
├── m4_semantic_graph/
│   ├── __init__.py
│   └── ...
tests/
├── test_m2_parser.py
├── test_m3_schema.py
├── test_m4_semantic_graph.py
└── conftest.py          # fixture 集中定义
```

- 测试文件 `test_*.py`，测试函数 `test_<行为>`，断言具体结果不写模糊注释。

### 2.2 纯逻辑模块用表驱动测试（M2/M3）

```python
# tests/test_m2_parser.py
import pytest

from autobranch.m2_parser import BehaviorTreeParser, ParseResult

EXPAND_CASES = [
    # (复合节点文档, 期望展开的基础节点结构)
    (
        {"Step": {"action": "点击登录", "expect": "出现工作台"}},
        [("Action", "点击登录"), ("Condition", "出现工作台")],
    ),
    (
        {"Retry": {"max": 3, "body": {"Action": "点击下载"}}},
        [("Repeat", {"mode": "retry", "max": 3})],
    ),
]


@pytest.mark.parametrize("doc, expected", EXPAND_CASES)
def test_compound_node_expansion(doc, expected):
    result: ParseResult = BehaviorTreeParser().parse(doc)
    assert flatten(result.tree) == expected
```

### 2.3 校验反例矩阵（§4.4）

对每类违规构造反例，断言报错信息可读：

```python
INVALID_CASES = [
    ({"LoopUntil": {"action": "..."}}, "missing_max", "循环必须有上界"),
    ({"ref": "不存在块/块名"}, "ref_not_found", "引用不存在"),
]


@pytest.mark.parametrize("doc, code, keyword", INVALID_CASES)
def test_clarity_check_rejects(doc, code, keyword):
    result = BehaviorTreeParser().parse(doc)
    assert not result.checks.passed
    assert any(code == c.code and keyword in c.message for c in result.checks.errors)
```

### 2.4 mock 依赖模块（M6 测 M5、M7 测 M6）

用 `pytest.raises` 校验引擎兜底终止条件：

```python
# tests/test_m6_leaf_agent.py
from unittest.mock import MagicMock


def test_leaf_terminates_after_max_rounds():
    session = FakeLLMSession(always_call_tool=True)   # 固定 LLM 桩
    functions = MagicMock()                            # mock M5
    result = execute_leaf(action_node, LeafContext(session=session, functions=functions))
    assert result.status == "failure"
    assert result.trace.terminator == "max_rounds"
```

- mock LLM：定义返回固定响应的桩（`FakeLLMSession`），**不**连真实 API。
- mock 语义图：`MagicMock(spec=SemanticGraph)` 只保留类型契约字段。

### 2.5 集成测试打标记

```python
# 真实浏览器 / 真实 LLM 的测试统一标记 integration
import pytest

pytestmark = pytest.mark.integration

def test_open_and_click_real_page():
    ...
```

## 3. 前端测试（Vitest + React Testing Library）

### 3.1 同目录放置测试文件

```
src/features/tree-editor/TreeEditorPage.test.tsx
```

### 3.2 组件测试：行为驱动，避免测试实现细节

```tsx
// TreeEditorPage.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../../api/trees";
import { TreeEditorPage } from "./TreeEditorPage";

vi.mock("../../api/trees", () => ({
  api: {
    listTrees: vi.fn(),
    saveTree: vi.fn(),
  },
}));

describe("TreeEditorPage", () => {
  it("渲染行为树列表，点击新建后调用保存", async () => {
    (api.listTrees as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: 1, name: "登录流程", created_at: "2026-01-01", updated_at: "2026-01-01" },
    ]);

    render(<TreeEditorPage />);
    await screen.findByText("登录流程");

    fireEvent.click(screen.getByRole("button", { name: "新建" }));
    await waitFor(() => expect(api.saveTree).toHaveBeenCalled());
  });
});
```

### 3.3 轮询 hook 测试：mock 状态序列

```tsx
// usePolling.test.ts
import { renderHook, waitFor } from "@testing-library/react";
import { usePolling } from "./usePolling";

it("执行未结束时持续轮询，finished 后停止", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce({ progress: 0.5, finished: false })
    .mockResolvedValueOnce({ progress: 1.0, finished: true });

  const { result } = renderHook(() =>
    usePolling(fetcher, (s) => s.finished, 10),
  );

  await waitFor(() => expect(result.current.data?.finished).toBe(true));
  expect(fetcher).toHaveBeenCalledTimes(2);
});
```

### 3.4 测试要点

- 查询优先 `getByRole` / `getByText`（用户视角），不用 `data-testid` 兜底，避免测试耦合 DOM 结构。
- mock 后端 API 时 `vi.mock` 模块级，返回值用 `mockResolvedValue`。
- **不在单测里测真实网络 / 真实浏览器**——那是 E2E 的职责。

## 4. E2E 测试（Playwright）

### 4.1 覆盖关键用户链路

**E2E 重点是「前端执行行为树 + 前端查看执行结果」**：

- 列表页定位行为树 → 点「执行」→ 跳转报告页。
- 报告页轮询渲染执行状态（进度 / 节点成功失败 / 截图）。
- 执行完成后切换查看「完整执行报告」与「回溯报告」。

**编辑器拖拽构建等复杂 UI 操作不是测试重点**——由组件测试覆盖；E2E 中
用 API 预置数据（Playwright `request` 经前端代理调 `/api/trees`），**不必
模拟拖拽**。

```ts
// e2e/workflow.spec.ts
import { expect, test, request as apiRequest } from "@playwright/test";

const TREE_NAME = `e2e执行${Date.now()}`;
const TREE_YAML = `操作块 ${TREE_NAME}:
  Step:
    action: 打开页面 "http://127.0.0.1:8123/index.html"
    expect: 页面出现"登录"
`;

test.beforeAll(async () => {
  const api = await apiRequest.newContext({ baseURL: "http://localhost:5174" });
  await api.post("/api/trees", { data: { name: TREE_NAME, content: TREE_YAML } });
  await api.dispose();
});

test("前端执行行为树并查看执行结果", async ({ page }) => {
  await page.goto("/");
  const row = page.locator('[data-testid^="tree-row-"]', { hasText: TREE_NAME });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "执行" }).click();
  await page.waitForURL(/\/runs\/\d+/);

  await expect(page.getByTestId("progress-text")).toHaveText(/进度：\d+%/, { timeout: 120_000 });
  const panel = page.getByTestId("report-panel");
  await expect(panel).toBeVisible({ timeout: 120_000 });

  await page.getByRole("button", { name: "完整执行报告" }).click();
  await expect(panel.locator("pre")).toContainText("执行情况报告");
  await page.getByRole("button", { name: "回溯报告" }).click();
  await expect(panel.locator("pre")).toContainText("回溯报告");
});
```

引擎层集成（真实页面 + 真实浏览器驱动）用 `pytest -m integration` 覆盖。

### 4.2 E2E 铁律

- E2E 数量精简，聚焦「执行 → 轮询 → 报告渲染」链路；编辑器交互、后端逻辑分别由组件测试 / pytest 兜住。
- 每个 E2E 测试**幂等可重复**：用独立数据（时间戳命名），测试前后清理。
- 用用户可见文案定位元素（`getByRole` / `getByText` / `getByTestId`），不用固定 sleep（用 `toBeVisible(timeout)` 等待）。
- 运行前提：前后端已启动（`dev-restart.ps1`：后端 8001 / 前端 5174），执行目标测试页可访问。
- 执行结果由后端决定（可能因缺 LLM 密钥返回明确错误）——E2E 断言「报告面板正确渲染结果」，不强求执行成功。

## 5. 通用铁律

1. **测试必须可重复**：不依赖网络/时间/随机；需要时注入或 mock。
2. **一个测试断言一个行为**：失败时定位准确。
3. **不测试实现细节**：测外部行为（返回值、调用契约），不测内部函数名/私有方法。
4. **mock 边界清晰**：mock 的是"接口契约"（类型），不是"行为"——mock 返回值要接近真实。
5. **跑一遍再提交**：任何改动后运行 `pytest`、`npm test`、`npm run typecheck`、`npm run lint`，确认全绿再交付。

## 6. Do's & Don'ts 速查

| Do ✅ | Don't ❌ |
|---|---|
| 纯逻辑模块表驱动参数化测试 | 每个用例单独写一段重复代码 |
| mock 外部依赖（LLM/浏览器/API） | 单测连真实网络 / 真实浏览器 |
| 断言具体结果与可读报错信息 | 只断言 `assert result is not None` |
| 集成/E2E 打标记（`-m integration`、`test:e2e`） | 把真实浏览器测试混进普通 pytest |
| 前端用 getByRole/getByText 用户视角查询 | 滥用 data-testid、测内部 state |
| 测试前清理、测试幂等 | 测试互相依赖、共享可变全局状态 |