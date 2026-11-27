import { expect, test, request as apiRequest } from "@playwright/test";

import { createTree } from "./helpers";

const API = { baseURL: "http://localhost:5174" };

test("G1 分组管理、移动与筛选", async ({ page }) => {
  const stamp = Date.now();
  const api = await apiRequest.newContext(API);
  const createdGroup = await api.post("/api/tree-groups", {
    data: { name: `E2E分组${stamp}` },
  });
  expect(createdGroup.ok()).toBeTruthy();
  const group = await createdGroup.json();
  const groups = await (await api.get("/api/tree-groups")).json();
  const defaultGroup = groups.find((item: { is_default: boolean }) => item.is_default);
  const tree = await createTree(api, `e2e分组树${stamp}`, `tree: e2e分组树${stamp}
nodes:
  n1: {type: Root, body: n2}
  n2: {type: Action, description: "无操作"}
root: n1
`);

  await page.goto("/");
  const row = page.locator(`[data-testid="tree-row-${tree.id}"]`);
  await expect(row).toBeVisible();
  await page.getByTestId(`tree-group-${tree.id}`).selectOption(String(group.id));
  await expect
    .poll(async () => (await (await api.get(`/api/trees/${tree.id}`)).json()).group_id)
    .toBe(group.id);

  await page.getByTestId("group-filter").selectOption(String(group.id));
  await expect(row).toBeVisible();
  await page.getByTestId("group-filter").selectOption("all");

  await page.getByTestId("manage-groups").click();
  await expect(page.getByTestId("group-manager")).toBeVisible();
  const nameInput = page.getByTestId(`group-name-${group.id}`);
  await nameInput.fill(`E2E改名${stamp}`);
  await page.getByTestId(`group-save-${group.id}`).click();
  await expect
    .poll(async () => {
      const list = await (await api.get("/api/tree-groups")).json();
      return list.find((item: { id: number }) => item.id === group.id)?.name;
    })
    .toBe(`E2E改名${stamp}`);
  await page.getByTestId("close-group-manager").click();

  await page.getByTestId(`tree-group-${tree.id}`).selectOption(String(defaultGroup.id));
  await page.getByTestId("manage-groups").click();
  await page.getByTestId(`group-delete-${group.id}`).click();
  await expect(page.getByTestId(`group-row-${group.id}`)).toHaveCount(0);
  await api.dispose();
});
