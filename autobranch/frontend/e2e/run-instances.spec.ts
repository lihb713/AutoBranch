import { expect, test, request as apiRequest } from "@playwright/test";

/**
 * Change A E2E：执行列表与实例化（任务 6.1/6.2）。
 *
 * 重点链路（按项目约定）：
 *  - 带可构造入参的树：列表页「执行」→ 入参对话框 → 报告页轮询 → 出参展示
 *  - 执行列表页：实例出现、状态、入参、重试（复制快照+入参）、查看快照
 *  - 含不可构造入参（page_ref）的树：不渲染「执行」按钮
 *
 * 用确定性 FunctionCall（compute.add）树，不经 LLM、不依赖测试页，避免随机性。
 * 前置：前后端已启动（dev-restart.ps1：后端 8001 / 前端 5174）。
 */

const COMPUTE_NAME = `计算${Date.now()}`;
// 确定性执行树：入参 a/b → compute.add → 出参 结果
const COMPUTE_YAML = `tree: ${COMPUTE_NAME}
inputs:
  a: int
  b: int
outputs:
  - 结果
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: FunctionCall
    name: 求和
    function: compute.add
    args: [Param.a, Param.b]
    returns: {结果: int}
root: n1
`;

const PAGE_REF_NAME = `页签树${Date.now()}`;
const PAGE_REF_YAML = `tree: ${PAGE_REF_NAME}
inputs:
  页: page_ref
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: Action
    name: 打开
    description: 打开 Param.页
root: n1
`;

test.beforeAll(async () => {
  const api = await apiRequest.newContext({ baseURL: "http://localhost:5174" });
  for (const tree of [
    { name: COMPUTE_NAME, content: COMPUTE_YAML },
    { name: PAGE_REF_NAME, content: PAGE_REF_YAML },
  ]) {
    const resp = await api.post("/api/trees", { data: tree });
    expect(resp.ok()).toBeTruthy();
  }
  await api.dispose();
});

test("带入参执行 → 报告出参 → 执行列表展示 → 重试", async ({ page }) => {
  // 1. 列表页定位带参树 → 点「执行」弹出入参对话框
  await page.goto("/");
  const row = page.locator('[data-testid^="tree-row-"]', { hasText: COMPUTE_NAME });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "执行" }).click();

  // 2. 填写入参 a=2, b=3 → 确认 → 跳转报告页
  const dialog = page.getByTestId("run-input-dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByTestId("input-value-a").fill("2");
  await dialog.getByTestId("input-value-b").fill("3");
  await dialog.getByTestId("run-dialog-confirm").click();
  await page.waitForURL(/\/runs\/\d+/);

  // 3. 报告页轮询到终态（进度条出现）→ 出参展示 {"结果": 5}
  await expect(page.getByTestId("progress-text")).toHaveText(/进度：\d+%/, {
    timeout: 120_000,
  });
  const outputs = page.getByTestId("outputs-section");
  await expect(outputs).toBeVisible({ timeout: 120_000 });
  await expect(outputs).toContainText('"结果": 5');

  // 4. 执行列表：实例出现、SUCCESS、入参 JSON 展示
  await page.goto("/runs");
  const runRow = page.locator('[data-testid^="run-row-"]', { hasText: COMPUTE_NAME }).first();
  await expect(runRow).toBeVisible();
  await expect(runRow).toContainText("SUCCESS");
  await expect(runRow).toContainText('{"a":2,"b":3}');

  // 5. 查看 → 跳转执行详情页：实例信息区展示状态/入参/出参/快照
  await runRow.locator('[data-testid^="run-view-"]').click();
  await page.waitForURL(/\/runs\/\d+/);
  const meta = page.getByTestId("run-meta");
  await expect(meta).toBeVisible();
  await expect(meta).toContainText("SUCCESS");
  await expect(meta).toContainText('"a": 2');
  await expect(meta).toContainText('"结果": 5');
  await page.getByText("执行快照（触发时刻的行为树内容）").click();
  await expect(page.getByTestId("snapshot-section")).toContainText("compute.add");

  // 6. 回列表重试：复制快照+入参 → 新实例
  await page.goto("/runs");
  await runRow.locator('[data-testid^="run-retry-"]').click();
  await page.waitForURL(/\/runs\/\d+/);
  await page.goto("/runs");
  const rows = page.locator('[data-testid^="run-row-"]', { hasText: COMPUTE_NAME });
  await expect(rows).toHaveCount(2);
  await expect(rows.first()).toContainText('{"a":2,"b":3}');
  await expect(rows.last()).toContainText('{"a":2,"b":3}');
});

test("含不可构造入参（page_ref）的树不渲染执行按钮", async ({ page }) => {
  await page.goto("/");
  const row = page.locator('[data-testid^="tree-row-"]', { hasText: PAGE_REF_NAME });
  await expect(row).toBeVisible();
  await expect(row.getByRole("button", { name: "执行" })).toHaveCount(0);
});