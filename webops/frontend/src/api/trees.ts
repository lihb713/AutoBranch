import type { CheckReport } from "../types/check";
import type { TreeCreate, TreeDetailOut, TreeOut, TreeUpdate } from "../types/tree";
import { request } from "./request";

export const treesApi = {
  listTrees: () => request<TreeOut[]>("/trees"),

  getTree: (id: number) => request<TreeDetailOut>(`/trees/${id}`),

  getTreeByName: (name: string) =>
    request<TreeDetailOut>(`/trees/by-name/${encodeURIComponent(name)}`),

  createTree: (payload: TreeCreate) =>
    request<TreeOut>("/trees", { method: "POST", body: JSON.stringify(payload) }),

  updateTree: (id: number, payload: TreeUpdate) =>
    request<TreeOut>(`/trees/${id}`, { method: "PUT", body: JSON.stringify(payload) }),

  deleteTree: (id: number) => request<void>(`/trees/${id}`, { method: "DELETE" }),

  checkTree: (id: number) =>
    request<CheckReport>(`/trees/${id}/check`, { method: "POST" }),
};