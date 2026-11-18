import { expect, test, request as apiRequest } from "@playwright/test";

import { createTree } from "./helpers";

const TREE_NAME = `导出树${Date.now()}`;
const TREE_YAML = `tree: ${TREE_NAME}
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: Action
    name: 操作
    description: 打开页面
root: n1
`;

test("行为树列表可导出 yaml 文档", async ({ page }) => {
  const api = await apiRequest.newContext({ baseURL: "http://localhost:5174" });
  await createTree(api, TREE_NAME, TREE_YAML);
  await api.dispose();

  await page.goto("/");
  const row = page.locator('[data-testid^="tree-row-"]', { hasText: TREE_NAME });
  await expect(row).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await row.locator('[data-testid^="export-"]').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain(TREE_NAME);
  expect(download.suggestedFilename()).toMatch(/\.yaml$/);
});
