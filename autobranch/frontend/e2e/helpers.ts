import type { APIRequestContext } from "@playwright/test";

/** 通过前端代理创建行为树；默认保存为正式版，便于执行。 */
export async function createTree(
  api: APIRequestContext,
  name: string,
  content: string,
  { publish = true }: { publish?: boolean } = {},
) {
  const resp = await api.post("/api/trees", { data: { name, content } });
  if (!resp.ok()) throw new Error(`创建行为树失败: ${resp.status()} ${await resp.text()}`);
  const tree = await resp.json();
  if (!publish) return tree;
  const saved = await api.post(`/api/trees/${tree.id}/save`);
  if (!saved.ok()) throw new Error(`保存行为树失败: ${saved.status()} ${await saved.text()}`);
  return saved.json();
}
