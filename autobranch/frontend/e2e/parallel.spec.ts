import { expect, test, request as apiRequest } from "@playwright/test";

import { createTree } from "./helpers";

/**
 * Parallel 端到端：前端执行确定性并发行为树，报告展示 SUCCESS 与并行标签。
 */

const API = { baseURL: "http://localhost:5174" };

test("P1 前端执行 Parallel 并查看并行报告", async ({ page }) => {
  const name = `e2eParallel${Date.now()}`;
  const content = `tree: ${name}
outputs: {rows: array}
nodes:
  n1:
    type: Root
    body: n2
  n2:
    type: Parallel
    variables:
      item: '["a","b","c"]'
    max_concurrency: 2
    on_failure: continue
    collect:
      target: rows
      fields: [result]
    body: n3
  n3:
    type: FunctionCall
    function: vars.set
    args: [Param.item]
    returns:
      result: str
root: n1
`;
  const api = await apiRequest.newContext(API);
  await createTree(api, name, content);
  await api.dispose();

  await page.goto("/");
  const row = page.locator('[data-testid^="tree-row-"]', { hasText: name });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "执行" }).click();
  await page.waitForURL(/\/runs\/\d+/);

  const panel = page.getByTestId("report-panel");
  await expect(panel).toContainText("SUCCESS", { timeout: 30_000 });
  await expect(panel).toContainText("Parallel#", { timeout: 30_000 });
  await expect(panel).toContainText("收集变量", { timeout: 30_000 });
  await expect(panel).not.toContainText("FAILURE");
  await expect(page.getByTestId("outputs-section")).toContainText("rows", {
    timeout: 30_000,
  });
});
