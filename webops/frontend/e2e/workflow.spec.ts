import { expect, test, request as apiRequest } from "@playwright/test";

/**
 * WebOps 端到端测试：聚焦「前端执行行为树 + 前端查看执行结果」链路。
 *
 * 测试重点（按项目约定）：
 *  - 前端执行行为树（列表页点「执行」→ 跳转报告页）
 *  - 前端查看执行结果（轮询渲染节点进度、执行报告 / 回溯报告切换查看）
 *
 * 非重点（不模拟前端，避免复杂 UI 操作）：
 *  - 编辑器拖拽构建行为树（由组件测试覆盖）
 *  - 后端 API 逻辑（由 pytest 覆盖）
 *
 * 前置：前后端已启动（dev-restart.ps1：后端 8001 / 前端 5174），
 * 本地测试页 http://127.0.0.1:8123 可访问（行为树执行目标）。
 */

const TREE_NAME = `e2e执行${Date.now()}`;
// 行为树（一文档一树，统一槽位）：打开本地测试页并断言页面出现「登录」
const TREE_YAML = `tree: ${TREE_NAME}
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: Step
    name: 打开登录页
    action: n3
    expect: 页面出现"登录"
  n3:
    type: Action
    name: 打开页面
    description: 打开页面 "http://127.0.0.1:8123/index.html"
root: n1
`;

test.beforeAll(async () => {
  // 经前端代理预置行为树（避免编辑器拖拽，编辑器由组件测试覆盖）
  const api = await apiRequest.newContext({ baseURL: "http://localhost:5174" });
  const resp = await api.post("/api/trees", { data: { name: TREE_NAME, content: TREE_YAML } });
  expect(resp.ok()).toBeTruthy();
  await api.dispose();
});

test("前端执行行为树并查看执行结果", async ({ page }) => {
  // 1. 列表页定位目标行为树
  await page.goto("/");
  const row = page.locator('[data-testid^="tree-row-"]', { hasText: TREE_NAME });
  await expect(row).toBeVisible();

  // 2. 点击「执行」→ 跳转报告页
  await row.getByRole("button", { name: "执行" }).click();
  await page.waitForURL(/\/runs\/\d+/);

  // 3. 报告页：轮询渲染执行状态（进度条出现即链路已通）
  await expect(page.getByTestId("progress-text")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("progress-text")).toHaveText(/进度：\d+%/, {
    timeout: 120_000,
  });

  // 4. 等待执行完成 → 报告面板出现
  const panel = page.getByTestId("report-panel");
  await expect(panel).toBeVisible({ timeout: 120_000 });

  // 5. 查看「完整执行报告」：验证执行真正成功（SUCCESS、无 FAILURE）
  await page.getByRole("button", { name: "完整执行报告" }).click();
  await expect(panel.locator("pre")).toContainText("执行情况报告");
  await expect(panel.locator("pre")).toContainText("打开页面");
  await expect(panel.locator("pre")).toContainText("SUCCESS");
  await expect(panel.locator("pre")).not.toContainText("FAILURE");

  // 6. 切换查看「回溯报告」（含 LLM 推理过程）
  await page.getByRole("button", { name: "回溯报告" }).click();
  await expect(panel.locator("pre")).toContainText("回溯报告");
});