import { expect, test, request as apiRequest } from "@playwright/test";

const DIR = `e2e-files-${Date.now()}`;

test("文件管理：新建目录、上传文件并按路径下载", async ({ page }) => {
  const api = await apiRequest.newContext({ baseURL: "http://localhost:5174" });
  const created = await api.post("/api/plugins/file/directories", {
    data: { path: DIR },
  });
  expect(created.ok(), await created.text()).toBe(true);
  await api.dispose();

  await page.goto("/plugins");
  await page.getByTestId("plugin-page-file-/file").click();
  await expect(page.getByRole("heading", { name: "文件管理" })).toBeVisible();
  const dirRow = page.locator('[data-testid^="file-dir-"]', { hasText: DIR });
  await expect(dirRow).toBeVisible();
  await dirRow.getByRole("button", { name: new RegExp(DIR) }).click();

  await expect(page.getByTestId("file-breadcrumbs")).toContainText(DIR);
  await page.getByTestId("file-upload-input").setInputFiles({
    name: "hello.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("hello-file-platform"),
  });
  const fileRow = page.locator('[data-testid^="file-row-"]', { hasText: "hello.txt" });
  await expect(fileRow).toBeVisible();
  await expect(fileRow).toContainText(`${DIR}/hello.txt`);

  const downloadPromise = page.waitForEvent("download");
  await fileRow.getByRole("link", { name: "下载" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("hello.txt");

  const cleanApi = await apiRequest.newContext({ baseURL: "http://localhost:5174" });
  const dirs = await cleanApi.get("/api/plugins/file/directories");
  const data = await dirs.json();
  const target = data.find((item: { path: string }) => item.path === DIR);
  if (target) await cleanApi.delete(`/api/plugins/file/directories/${target.id}`);
  await cleanApi.dispose();
});
