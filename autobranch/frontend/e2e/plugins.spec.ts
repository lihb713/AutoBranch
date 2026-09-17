import { expect, test, request as apiRequest } from "@playwright/test";

/**
 * 插件管理端到端测试：覆盖「前端新增/编辑/删除自定义插件 + 保存校验 + 删除关联置空」。
 *
 * 前置：前后端已启动（后端 8001 / 前端 5174）。
 */

const API = { baseURL: "http://localhost:5174" };

const uniqueName = () =>
  `e2e-plugin-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
const makeSource = (name: string) => [
  "class E2EPlugin(PluginBase):",
  `    name = "${name}"`,
  '    description = "E2E 自定义插件"',
  "",
  '    @engine_function(',
  '        name="greet",',
  '        description="问候",',
  '        parameters={',
  '            "type": "object",',
  '            "properties": {"who": {"type": "string", "description": "对象"}},',
  '            "required": ["who"],',
  "        },",
  '        returns=("message",),',
  "    )",
  '    def greet(self, who="world"):',
  '        return f"hi {who}"',
  "",
  "plugin = E2EPlugin()",
  "",
].join("\n");

test("P1 插件列表展示预置插件徽标与函数", async ({ page }) => {
  await page.goto("/plugins");
  await expect(page.getByText("browser", { exact: true })).toBeVisible();
  await expect(page.getByText("compute", { exact: true })).toBeVisible();
  const row = page.locator("tr", { hasText: "browser" });
  await expect(row.getByText("预置")).toBeVisible();
  await expect(row.getByText("browser.open")).toBeVisible();
});

test("P2 新增自定义插件并保存生效", async ({ page }) => {
  const PLUGIN_NAME = uniqueName();
  const PLUGIN_SOURCE = makeSource(PLUGIN_NAME);
  await page.goto("/plugins");
  await page.getByRole("link", { name: "新增插件" }).click();
  await page.getByLabel("插件名").fill(PLUGIN_NAME);
  await page.locator(".cm-content").fill(PLUGIN_SOURCE);
  await page.getByRole("button", { name: "保存" }).click();
  await page.waitForURL(/\/plugins$/);
  const row = page.locator("tr", { hasText: PLUGIN_NAME });
  await expect(row).toBeVisible();
  await expect(row.getByText("自定义", { exact: true })).toBeVisible();
  await expect(row.getByText(`${PLUGIN_NAME}.greet`)).toBeVisible();
});

test("P3 编辑自定义插件并保存生效", async ({ page }) => {
  const PLUGIN_NAME = uniqueName();
  const PLUGIN_SOURCE = makeSource(PLUGIN_NAME);
  // 先用 API 建一个插件
  const api = await apiRequest.newContext(API);
  const created = await api.post("/api/plugins", {
    data: { name: PLUGIN_NAME, source: PLUGIN_SOURCE },
  });
  expect(created.ok()).toBeTruthy();
  await api.dispose();

  const edited = PLUGIN_SOURCE.replace('"E2E 自定义插件"', '"升级版描述"');
  await page.goto(`/plugins/edit/${PLUGIN_NAME}`);
  await expect(page.getByRole("heading", { name: /编辑插件/ })).toBeVisible();
  await page.locator(".cm-content").fill(edited);
  await page.getByRole("button", { name: "保存" }).click();
  await page.waitForURL(/\/plugins$/);
  const row = page.locator("tr", { hasText: PLUGIN_NAME });
  await expect(row.getByText("升级版描述")).toBeVisible();
});

test("P4 删除插件时弹窗提示关联并置空引用", async ({ page }) => {
  const PLUGIN_NAME = uniqueName();
  const PLUGIN_SOURCE = makeSource(PLUGIN_NAME);
  const api = await apiRequest.newContext(API);
  await api.post("/api/plugins", { data: { name: PLUGIN_NAME, source: PLUGIN_SOURCE } });
  const treeName = `e2e引用${Date.now()}`;
  const treeYaml = `tree: ${treeName}
nodes:
  n1:
    type: Root
    body: n2
  n2:
    type: FunctionCall
    function: ${PLUGIN_NAME}.greet
    args: ["world"]
    returns:
      问候: str
root: n1
`;
  const treeResp = await api.post("/api/trees", {
    data: { name: treeName, content: treeYaml },
  });
  expect(treeResp.ok()).toBeTruthy();
  const tree = await treeResp.json();
  await api.dispose();

  // 前端删除：confirm 弹窗应列出关联行为树
  page.once("dialog", (dialog) => {
    expect(dialog.message()).toContain(treeName);
    void dialog.accept();
  });
  await page.goto("/plugins");
  const row = page.locator("tr", { hasText: PLUGIN_NAME });
  await row.getByRole("button", { name: "删除" }).click();
  await expect(page.locator("tr", { hasText: PLUGIN_NAME })).toHaveCount(0);

  // 行为树 FunctionCall 引用被置空（持久化）
  const api2 = await apiRequest.newContext(API);
  const updatedResp = await api2.get(`/api/trees/${tree.id}`);
  expect(updatedResp.ok()).toBeTruthy();
  const updated = await updatedResp.json();
  expect(updated.content).toContain("function: null");
  expect(updated.content).not.toContain(`function: ${PLUGIN_NAME}.greet`);
  await api2.dispose();
});

test("P5 保存非法插件显示行号校验错误", async ({ page }) => {
  await page.goto("/plugins/new");
  await page.getByLabel("插件名").fill("bad-plugin");
  await page.locator(".cm-content").fill("import requests\nplugin = None\n");
  await page.getByRole("button", { name: "保存" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByText(/第 \d+ 行/)).toBeVisible();
  await expect(page.getByText(/仅标准库/)).toBeVisible();
});