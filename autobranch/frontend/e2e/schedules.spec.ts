import { expect, test, request as apiRequest } from "@playwright/test";

import { createTree } from "./helpers";

/**
 * M10 调度 E2E：调度页面 → 自动触发 → 执行列表来源/状态 → 报告页。
 *
 * 用确定性 FunctionCall（compute.add）树，不依赖 LLM；调度规则由 API 预置，
 * 前端只验证调度管理与执行结果展示链路。
 */

const TREE_NAME = `调度计算${Date.now()}`;
const COMPUTE_YAML = `tree: ${TREE_NAME}
inputs:
  a: int
  b: int
outputs:
  total: int
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
    returns: {total: int}
root: n1
`;

test("调度管理页：自动触发执行 → 来源标注 → 查看报告", async ({ page }) => {
  const api = await apiRequest.newContext({ baseURL: "http://localhost:5174" });
  const tree = await createTree(api, TREE_NAME, COMPUTE_YAML);
  const created = await api.post("/api/schedules", {
    data: {
      name: `调度规则${Date.now()}`,
      target_tree_id: tree.id,
      schedule_mode: "interval",
      interval: 1,
      interval_unit: "days",
      dependencies: [],
      on_failure: "immediate",
      max_retries: 1,
      retry_interval: 5,
      on_missed: "run",
      inputs: { a: 2, b: 3 },
      enabled: true,
    },
  });
  expect(created.ok(), await created.text()).toBe(true);
  const rule = await created.json();
  await api.dispose();

  // 1. 调度管理页展示规则
  await page.goto("/schedules");
  const row = page.getByTestId(`schedule-row-${rule.id}`);
  await expect(row).toBeVisible();
  await expect(row).toContainText(TREE_NAME);

  // 2. 等待调度线程自动触发（首次 last_run_at 为空 → 首次执行）
  await page.goto("/runs");
  const runRows = page.locator('[data-testid^="run-row-"]', { hasText: TREE_NAME });
  await expect(runRows.first()).toBeVisible({ timeout: 30_000 });
  await expect(runRows.first()).toContainText("SUCCESS");
  await expect(
    runRows.first().locator('[data-testid^="run-source-"]')
  ).toHaveText("调度");
  await expect(runRows.first()).toContainText('{"a":2,"b":3}');

  // 3. 调度页「立即执行」再触发一次
  await page.goto("/schedules");
  await page.getByTestId(`schedule-run-now-${rule.id}`).click();
  await expect(page.getByTestId("schedule-notice")).toContainText("已触发执行");
  await page.goto("/runs");
  await expect(runRows).toHaveCount(2, { timeout: 30_000 });

  // 4. 调度执行记录：居中弹窗 → 含依赖视图 → 跳转执行详情
  await page.goto("/schedules");
  await page.getByTestId(`schedule-runs-${rule.id}`).click();
  const records = page.getByTestId("schedule-records");
  await expect(records).toBeVisible();
  await page.getByTestId("schedule-records-all").click();
  await expect(records.locator('[data-testid^="schedule-record-view-"]').first()).toBeVisible();
  await records.locator('[data-testid^="schedule-record-view-"]').first().click();
  await page.waitForURL(/\/runs\/\d+/);

  // 5. 执行详情：来源/调度规则 → 报告轮询 → 出参
  await expect(page.getByTestId("run-source-label")).toHaveText("调度");
  await expect(page.getByTestId("run-schedule-info")).toContainText(rule.name);
  await expect(page.getByTestId("run-schedule-info")).toContainText("每 1 天");
  await expect(page.getByTestId("progress-text")).toHaveText(/进度：\d+%/, {
    timeout: 120_000,
  });
  await expect(page.getByTestId("outputs-section")).toContainText('"total": 5', {
    timeout: 120_000,
  });
});

test("前端新建调度时按目标行为树入参动态渲染表单", async ({ page }) => {
  const api = await apiRequest.newContext({ baseURL: "http://localhost:5174" });
  const name = `调度入参${Date.now()}`;
  const content = `tree: ${name}
inputs:
  count: int
  enabled: bool
  title: str
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: FunctionCall
    name: 求和
    function: compute.add
    args: [Param.count, Param.count]
    returns: {total: int}
root: n1
`;
  await createTree(api, name, content);
  await api.dispose();

  const ruleName = `入参规则${Date.now()}`;
  await page.goto("/schedules");
  await page.getByTestId("new-schedule").click();
  await page.getByTestId("schedule-name").fill(ruleName);
  await page.getByTestId("schedule-tree").selectOption({ label: name });
  await expect(page.getByTestId("schedule-input-count")).toBeVisible();
  await expect(page.getByTestId("schedule-input-enabled")).toBeVisible();
  await expect(page.getByTestId("schedule-input-title")).toBeVisible();
  await page.getByTestId("schedule-input-count").fill("3");
  await page.getByTestId("schedule-input-enabled").check();
  await page.getByTestId("schedule-input-title").fill("日报");
  await page.getByTestId("schedule-save").click();
  await expect(page.getByTestId("schedule-table")).toContainText(ruleName);
});
