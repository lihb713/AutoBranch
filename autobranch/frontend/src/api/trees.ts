import type { CheckReport } from "../types/check";
import type {
  TreeCommand,
  TreeCommandsOut,
  TreeCreate,
  TreeDetailOut,
  TreeOut,
  TreeUpdate,
} from "../types/tree";
import { request } from "./request";

export const treesApi = {
  listTrees: (publishedOnly = false) =>
    request<TreeOut[]>(`/trees${publishedOnly ? "?published_only=true" : ""}`),

  getTree: (id: number) => request<TreeDetailOut>(`/trees/${id}`),

  getTreeByName: (name: string) =>
    request<TreeDetailOut>(`/trees/by-name/${encodeURIComponent(name)}`),

  createTree: (payload: TreeCreate) =>
    request<TreeOut>("/trees", { method: "POST", body: JSON.stringify(payload) }),

  createDraft: () =>
    request<TreeOut>("/trees/drafts", { method: "POST" }),

  updateTree: (id: number, payload: TreeUpdate) =>
    request<TreeOut>(`/trees/${id}`, { method: "PUT", body: JSON.stringify(payload) }),

  applyCommands: (id: number, commands: TreeCommand[]) =>
    request<TreeCommandsOut>(`/trees/${id}/commands`, {
      method: "POST",
      body: JSON.stringify({ commands }),
    }),

  saveTree: (id: number, name?: string) =>
    request<TreeDetailOut>(`/trees/${id}/save`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  deleteTree: (id: number) => request<void>(`/trees/${id}`, { method: "DELETE" }),

  checkTree: (id: number) =>
    request<CheckReport>(`/trees/${id}/check`, { method: "POST" }),
};
