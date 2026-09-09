import { expect, test, request as apiRequest } from "@playwright/test";

/**
 * WebOps 端到端测试：嵌套块引用（ref 动态调用）执行链路。
 *
 * 覆盖 Plan ③ 核心特性：主流程 ref 一个命名块（args 传实参 / returns 收返回值），
 * 前端执行 → 轮询渲染 → 报告展示，验证动态调用在真实浏览器 + 真实 LLM 下可用。
 *
 * 前置：前后端已启动（后端 8001 / 前端 5174），本地测试页 127.0.0.1:8123 可访问。
 */

const TREE_NAME = `e2e-ref-${Date.now()}`;
// 注意：普通字符串，不用模板字面量拼接，避免 [[ ]] 与 ${} 冲突
const TREE_YAML =
  "block " + TREE_NAME + ":\n" +
  "  Sequence:\n" +
  "    - ref: this/打开页面\n" +
  "      args: {url: \"http://127.0.0.1:8123/index.html\"}\n" +
  "      returns: {url文本: this/当前url}\n" +
  "    - Step:\n" +
  "        action: 校验当前页面出现\"WebOps 测试站\"且记录的url含8123 [[get:this/当前url]]\n" +
  "        expect: 页面出现\"WebOps 测试站\"\n" +
  "\n" +
  "block 打开页面:\n" +
  "  inputs: {url: str}\n" +
  "  outputs: url文本\n" +
  "  Sequence:\n" +
  "    - Step:\n" +
  "        action: 打开页面 [[get:this/url]] 存页签 [[set:page_ref:this/页签]]\n" +
  "        expect: 页面出现\"登录\"\n" +
  "    - Step:\n" +
  "        action: 记录当前页地址 [[set:str:this/url文本]]\n" +
  "        expect: url 非空\n";

test.beforeAll(async () => {
  const api = await apiRequest.newContext({ baseURL: "http://localhost:5174" });
  const resp = await api.post("/api/trees", { data: { name: TREE_NAME, content: TREE_YAML } });
  expect(resp.ok()).toBeTruthy();
  await api.dispose();
});

test("前端执行含嵌套 ref 的行为树并查看执行结果", async ({ page }) => {
  // 1. 列表页定位目标行为树
  await page.goto("/");
  const row = page.locator('[data-testid^="tree-row-"]', { hasText: TREE_NAME });
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

  // 5. 完整执行报告：应包含 ref 调用块「打开页面」的执行记录
  await page.getByRole("button", { name: "完整执行报告" }).click();
  await expect(panel.locator("pre")).toContainText("执行情况报告");
  await expect(panel.locator("pre")).toContainText("打开页面");
  await expect(panel.locator("pre")).toContainText("打开页面");

  // 6. 回溯报告（含 LLM 推理过程）
  await page.getByRole("button", { name: "回溯报告" }).click();
  await expect(panel.locator("pre")).toContainText("回溯报告");
});