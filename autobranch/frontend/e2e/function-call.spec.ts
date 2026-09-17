import { expect, test, request as apiRequest } from "@playwright/test";

/**
 * FunctionCall 节点端到端测试：覆盖「前端渲染 FunctionCall 节点 / 确定性执行 /
 * 未知函数校验 / 叶子两级能力选择执行」。
 *
 * 前置：前后端已启动（后端 8001 / 前端 5174），LLM API 已配置（执行类用例）。
 */

const API = { baseURL: "http://localhost:5174" };

function treeYaml(name: string, body: string): string {
  return `tree: ${name}
nodes:
  n1:
    type: Root
    body: n2
  n2:
${body}
root: n1
`;
}

const MULTIPLY_TREE = (name: string) =>
  treeYaml(
    name,
    [
      "    type: FunctionCall",
      "    function: compute.multiply",
      '    args: ["2", "3"]',
      "    returns:",
      "      NewParam.result: int",
    ].join("\n"),
  );

const UNKNOWN_FN_TREE = (name: string) =>
  treeYaml(name, "    type: FunctionCall\n    function: compute.nope\n    args: []");

const CAPABILITY_TREE = (name: string) =>
  treeYaml(
    name,
    [
      "    type: Action",
      "    description: 计算 2 乘 3 并把结果写入变量 result NewParam.result:int",
    ].join("\n"),
  );

test("F1 编辑器渲染 FunctionCall 节点与函数名", async ({ page }) => {
  const name = `e2eFC渲染${Date.now()}`;
  const api = await apiRequest.newContext(API);
  const resp = await api.post("/api/trees", {
    data: { name, content: MULTIPLY_TREE(name) },
  });
  expect(resp.ok()).toBeTruthy();
  const tree = await resp.json();
  await api.dispose();

  await page.goto(`/editor/${tree.id}`);
  await expect(page.locator('[data-testid^="node-card-"]').first()).toBeVisible();
  // FunctionCall 节点卡片应显示函数全名 compute.multiply
  await expect(page.getByText("compute.multiply", { exact: false })).toBeVisible();
});

test("F2 FunctionCall 行为树执行成功并写变量", async ({ page }) => {
  const name = `e2eFC执行${Date.now()}`;
  const api = await apiRequest.newContext(API);
  const resp = await api.post("/api/trees", {
    data: { name, content: MULTIPLY_TREE(name) },
  });
  expect(resp.ok()).toBeTruthy();
  await api.dispose();

  await page.goto("/");
  const row = page.locator('[data-testid^="tree-row-"]', { hasText: name });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "执行" }).click();
  await page.waitForURL(/\/runs\/\d+/);

  const panel = page.getByTestId("report-panel");
  await expect(panel).toBeVisible({ timeout: 120_000 });

  // 完整执行报告：SUCCESS、无 FAILURE
  await page.getByRole("button", { name: "完整执行报告" }).click();
  await expect(panel.locator("pre")).toContainText("SUCCESS");
  await expect(panel.locator("pre")).not.toContainText("FAILURE");

  // 黑板变量：返回值 6 已回收写入「result」
  const blackboard = page.getByTestId("blackboard-panel");
  await expect(blackboard).toBeVisible({ timeout: 10_000 });
  await expect(blackboard.locator("tr", { hasText: "result" })).toContainText("6");
});

test("F3 未知函数校验失败", async ({ page }) => {
  const name = `e2eFC未知${Date.now()}`;
  const api = await apiRequest.newContext(API);
  const resp = await api.post("/api/trees", {
    data: { name, content: UNKNOWN_FN_TREE(name) },
  });
  // 函数不存在 → 保存被 422 拒绝
  expect(resp.status()).toBe(422);
  await api.dispose();
});

test("C1 叶子经两级能力选择执行并调用插件函数", async ({ page }) => {
  const name = `e2e能力${Date.now()}`;
  const api = await apiRequest.newContext(API);
  const resp = await api.post("/api/trees", {
    data: { name, content: CAPABILITY_TREE(name) },
  });
  expect(resp.ok()).toBeTruthy();
  await api.dispose();

  await page.goto("/");
  const row = page.locator('[data-testid^="tree-row-"]', { hasText: name });
  await row.getByRole("button", { name: "执行" }).click();
  await page.waitForURL(/\/runs\/\d+/);

  const panel = page.getByTestId("report-panel");
  await expect(panel).toBeVisible({ timeout: 120_000 });
  await page.getByRole("button", { name: "完整执行报告" }).click();
  await expect(panel.locator("pre")).toContainText("SUCCESS");
  await expect(panel.locator("pre")).not.toContainText("FAILURE");
});

/**
 * F5 完整链路（真实浏览器 + 计算插件）：浏览器登录测试页 → 分别提取苹果/香蕉金额 → FunctionCall 求和。
 * 前置：测试页 http://127.0.0.1:8123/summary.html 可访问、LLM 已配置。
 */
test("F5 浏览器登录测试页 + 提取苹果香蕉金额并求和（完整链路）", async ({ page }) => {
  const name = `e2e完整链路${Date.now()}`;
  const yaml = `tree: ${name}
nodes:
  n1:
    type: Root
    body: n2
  n2:
    type: Sequence
    actions: [登录步骤, 提取苹果, 提取香蕉, 求和]
  登录步骤:
    type: Step
    action: 登录动作
    expect: 页面出现"销售数据表"
  登录动作:
    type: Action
    description: 打开 http://127.0.0.1:8123/summary.html，在用户名输入框输入 admin，密码输入框输入 secret，点击登录按钮
  提取苹果:
    type: Action
    description: 用 extract 提取表格中"苹果"那一行的金额列值，写入变量 appleAmount NewParam.appleAmount:int
  提取香蕉:
    type: Action
    description: 用 extract 提取表格中"香蕉"那一行的金额列值，写入变量 bananaAmount NewParam.bananaAmount:int
  求和:
    type: FunctionCall
    function: compute.add
    args: [Param.appleAmount, Param.bananaAmount]
    returns:
      NewParam.fruitTotal: int
root: n1
`;
  const api = await apiRequest.newContext(API);
  const resp = await api.post("/api/trees", { data: { name, content: yaml } });
  expect(resp.ok()).toBeTruthy();
  await api.dispose();

  await page.goto("/");
  const row = page.locator('[data-testid^="tree-row-"]', { hasText: name });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "执行" }).click();
  await page.waitForURL(/\/runs\/\d+/);

  const panel = page.getByTestId("report-panel");
  await expect(panel).toBeVisible({ timeout: 180_000 });
  await page.getByRole("button", { name: "完整执行报告" }).click();
  await expect(panel.locator("pre")).toContainText("SUCCESS");
  await expect(panel.locator("pre")).not.toContainText("FAILURE");
  // 变量落笔：appleAmount 120 + bananaAmount 35 = 155（黑板）
  await expect(page.getByText("155")).toBeVisible({ timeout: 20_000 });
});