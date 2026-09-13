import { expect, test, request as apiRequest } from "@playwright/test";

/**
 * WebOps 端到端测试：跨文档引用（ref 动态调用）执行链路。
 *
 * 覆盖一文档一树核心特性：文档 A ref 文档 B（args 传实参 / returns 收返回值），
 * 前端执行 A → 轮询渲染 → 报告展示，验证跨文档动态调用在真实浏览器 + 真实 LLM 下可用。
 *
 * 前置：前后端已启动（后端 8001 / 前端 5174），本地测试页 127.0.0.1:8123 可访问。
 */

const STAMP = Date.now();
const A_NAME = `e2e-refA-${STAMP}`;
const B_NAME = `e2e-refB-${STAMP}`;

// 注意：普通字符串拼接，避免 [[ ]] 与模板字面量 ${} 冲突
const B_YAML =
  "tree: " + B_NAME + "\n" +
  "inputs: {url: str}\n" +
  "outputs: [url文本]\n" +
  "nodes:\n" +
  "  n1:\n    type: Root\n    name: 根\n    body: n2\n" +
  "  n2:\n    type: Sequence\n    name: 打开页面\n    actions: [n3, n4]\n" +
  "  n3:\n    type: Step\n    name: 打开\n    action: n5\n    expect: 页面出现\"登录\"\n" +
  "  n5:\n    type: Action\n    name: 打开动作\n" +
  "    description: 打开页面 [[get:this/url]] 存页签 [[set:page_ref:this/页签]]\n" +
  "  n4:\n    type: Step\n    name: 记录地址\n    action: n6\n    expect: url 非空\n" +
  "  n6:\n    type: Action\n    name: 记录\n" +
  "    description: 记录当前页地址 [[set:str:this/url文本]]\n" +
  "root: n1\n";

const A_YAML =
  "tree: " + A_NAME + "\n" +
  "nodes:\n" +
  "  n1:\n    type: Root\n    name: 根\n    body: n2\n" +
  "  n2:\n    type: Sequence\n    name: 主流程\n    actions: [n3, n4]\n" +
  "  n3:\n    type: ref\n    name: 打开页面\n" +
  "    target: " + B_NAME + "\n" +
  "    args: [\"http://127.0.0.1:8123/index.html\"]\n" +
  "    returns: {url文本: str}\n" +
  "  n4:\n    type: Step\n    name: 校验\n    action: n5\n    expect: 页面出现\"WebOps 测试站\"\n" +
  "  n5:\n    type: Action\n    name: 校验动作\n" +
  "    description: 校验当前页面出现\"WebOps 测试站\" [[get:this/url文本]]\n" +
  "root: n1\n";

test.beforeAll(async () => {
  const api = await apiRequest.newContext({ baseURL: "http://localhost:5174" });
  const rb = await api.post("/api/trees", { data: { name: B_NAME, content: B_YAML } });
  expect(rb.ok()).toBeTruthy();
  const ra = await api.post("/api/trees", { data: { name: A_NAME, content: A_YAML } });
  expect(ra.ok()).toBeTruthy();
  await api.dispose();
});

test("前端执行跨文档引用的行为树并查看执行结果", async ({ page }) => {
  // 1. 列表页定位引用文档 A
  await page.goto("/");
  const row = page.locator('[data-testid^="tree-row-"]', { hasText: A_NAME });
  await expect(row).toBeVisible();

  // 2. 点击「执行」→ 跳转报告页
  await row.getByRole("button", { name: "执行" }).click();
  await page.waitForURL(/\/runs\/\d+/);

  // 3. 报告页：轮询渲染执行状态
  await expect(page.getByTestId("progress-text")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("progress-text")).toHaveText(/进度：\d+%/, {
    timeout: 120_000,
  });

  // 4. 等待执行完成 → 报告面板出现
  const panel = page.getByTestId("report-panel");
  await expect(panel).toBeVisible({ timeout: 120_000 });

  // 5. 完整执行报告：应包含被引文档 B 的叶子执行记录，且执行真正成功
  await page.getByRole("button", { name: "完整执行报告" }).click();
  await expect(panel.locator("pre")).toContainText("执行情况报告");
  await expect(panel.locator("pre")).toContainText("打开页面");
  await expect(panel.locator("pre")).toContainText("SUCCESS");
  await expect(panel.locator("pre")).not.toContainText("FAILURE");

  // 6. 回溯报告（含 LLM 推理过程）
  await page.getByRole("button", { name: "回溯报告" }).click();
  await expect(panel.locator("pre")).toContainText("回溯报告");
});