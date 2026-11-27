import type { CheckReport } from "../types/check";
import type {
  TreeCommand,
  TreeGroup,
  TreeCommandsOut,
  TreeCreate,
  TreeDetailOut,
  TreeOut,
  TreeUpdate,
} from "../types/tree";
import { request } from "./request";

export const treesApi = {
  listTrees: (publishedOnly = false, groupId?: number) => {
    const params = new URLSearchParams();
    if (publishedOnly) params.set("published_only", "true");
    if (groupId !== undefined) params.set("group_id", String(groupId));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request<TreeOut[]>(`/trees${suffix}`);
  },

  listTreeGroups: () => request<TreeGroup[]>("/tree-groups"),

  createTreeGroup: (name: string) =>
    request<TreeGroup>("/tree-groups", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  renameTreeGroup: (id: number, name: string) =>
    request<TreeGroup>(`/tree-groups/${id}`, {
      method: "PUT",
      body: JSON.stringify({ name }),
    }),

  deleteTreeGroup: (id: number) =>
    request<void>(`/tree-groups/${id}`, { method: "DELETE" }),

  moveTreeGroup: (treeId: number, groupId: number) =>
    request<TreeOut>(`/trees/${treeId}/group`, {
      method: "PATCH",
      body: JSON.stringify({ group_id: groupId }),
    }),

  getTree: (id: number) => request<TreeDetailOut>(`/trees/${id}`),

  getTreeByName: (name: string) =>
    request<TreeDetailOut>(`/trees/by-name/${encodeURIComponent(name)}`),

  createTree: (payload: TreeCreate) =>
    request<TreeOut>("/trees", { method: "POST", body: JSON.stringify(payload) }),

  createDraft: (groupId?: number) =>
    request<TreeOut>(
      `/trees/drafts${groupId !== undefined ? `?group_id=${groupId}` : ""}`,
      { method: "POST" },
    ),

  updateTree: (id: number, payload: TreeUpdate) =>
    request<TreeOut>(`/trees/${id}`, { method: "PUT", body: JSON.stringify(payload) }),

  applyCommands: (id: number, commands: TreeCommand[]) =>
    request<TreeCommandsOut>(`/trees/${id}/commands`, {
      method: "POST",
      body: JSON.stringify({ commands }),
    }),

  saveTree: (id: number, name?: string, description?: string) =>
    request<TreeDetailOut>(`/trees/${id}/save`, {
      method: "POST",
      body: JSON.stringify({ name, description }),
    }),

  deleteTree: (id: number) => request<void>(`/trees/${id}`, { method: "DELETE" }),

  checkTree: (id: number) =>
    request<CheckReport>(`/trees/${id}/check`, { method: "POST" }),
};
