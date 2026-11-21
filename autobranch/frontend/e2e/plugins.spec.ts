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
  '        returns={"message": "str"},',
  "    )",
  '    def greet(self, who="world"):',
  '        return f"hi {who}"',
  "",
  "plugin = E2EPlugin()",
  "",
].join("\n");

test("P1 插件卡片展示 manifest/配置入口与函数详情", async ({ page }) => {
  await page.goto("/plugins");
  await expect(page.getByTestId("plugin-card-browser")).toBeVisible();
  await expect(page.getByTestId("plugin-card-compute")).toBeVisible();
  await expect(page.getByTestId("plugin-card-browser").getByText("预置")).toBeVisible();
  await expect(page.getByTestId("plugin-types-browser")).toContainText("page_object");
  await expect(page.getByTestId("plugin-types-ssh")).toContainText("ssh_session");

  const fileCard = page.getByTestId("plugin-card-file");
  await expect(fileCard.getByTestId("plugin-config-file")).toBeVisible();
  await expect(fileCard.getByTestId("plugin-page-file-/file")).toBeVisible();

  // 函数详情页展示全部函数与可见性（含 LLM-only）
  await page.goto("/plugins/edit/browser");
  await expect(page.getByTestId("plugin-tab-functions")).toBeVisible();
  await expect(page.getByText("browser.open", { exact: false })).toBeVisible();
  await page.getByTestId("plugin-tab-source").click();
  await expect(page.getByText("预置插件只读", { exact: false })).toBeVisible();
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
  const card = page.getByTestId(`plugin-card-${PLUGIN_NAME}`);
  await expect(card).toBeVisible();
  await expect(card.getByText("自定义", { exact: true })).toBeVisible();
  await card.getByText("查看函数详情").click();
  await expect(page.getByText(`${PLUGIN_NAME}.greet`, { exact: false })).toBeVisible();
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
  await expect(page.getByRole("heading", { name: /插件/ })).toBeVisible();
  await page.getByTestId("plugin-tab-source").click();
  await page.locator(".cm-content").fill(edited);
  await page.getByRole("button", { name: "保存" }).click();
  await page.waitForURL(/\/plugins$/);
  const card = page.getByTestId(`plugin-card-${PLUGIN_NAME}`);
  await expect(card.getByText("升级版描述")).toBeVisible();
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
      greeting: str
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
  const card = page.getByTestId(`plugin-card-${PLUGIN_NAME}`);
  await card.getByTestId(`plugin-delete-${PLUGIN_NAME}`).click();
  await expect(page.getByTestId(`plugin-card-${PLUGIN_NAME}`)).toHaveCount(0);

  // 行为树 FunctionCall 引用被置空（持久化）
  const api2 = await apiRequest.newContext(API);
  const updatedResp = await api2.get(`/api/trees/${tree.id}`);
  expect(updatedResp.ok()).toBeTruthy();
  const updated = await updatedResp.json();
  expect(updated.content).toContain("function: null");
  expect(updated.content).not.toContain(`function: ${PLUGIN_NAME}.greet`);
  await api2.dispose();
});

test("P6 文件管理插件页面：上传/列表/删除", async ({ page }) => {
  await page.goto("/plugins");
  await page.getByTestId("plugin-page-file-/file").click();
  await page.waitForURL(/\/file$/);
  await expect(page.getByTestId("file-manager")).toBeVisible();

  const name = `e2e-file-${Date.now()}.txt`;
  await page.getByTestId("file-upload-input").setInputFiles({
    name,
    mimeType: "text/plain",
    buffer: Buffer.from("hello-file-manager"),
  });
  const row = page.locator('[data-testid^="file-row-"]', { hasText: name });
  await expect(row).toBeVisible();
  page.once("dialog", (dialog) => void dialog.accept());
  await row.getByRole("button", { name: "删除" }).click();
  await expect(row).toHaveCount(0);
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