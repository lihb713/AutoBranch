import type {
  FunctionInfo,
  PluginCheckOut,
  PluginCreate,
  PluginDeleteOut,
  PluginDetailOut,
  PluginOut,
  PluginUpdate,
} from "../types/plugin";
import { request } from "./request";

export const pluginsApi = {
  listPlugins: () => request<PluginOut[]>("/plugins"),

  listFunctions: () => request<FunctionInfo[]>("/functions"),

  getPlugin: (name: string) =>
    request<PluginDetailOut>(`/plugins/${encodeURIComponent(name)}`),

  createPlugin: (payload: PluginCreate) =>
    request<PluginOut>("/plugins", { method: "POST", body: JSON.stringify(payload) }),

  updatePlugin: (name: string, payload: PluginUpdate) =>
    request<PluginOut>(`/plugins/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  deletePlugin: (name: string) =>
    request<PluginDeleteOut>(`/plugins/${encodeURIComponent(name)}`, { method: "DELETE" }),

  checkPlugin: (payload: PluginCreate) =>
    request<PluginCheckOut>("/plugins/check", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listReferences: (name: string) =>
    request<string[]>(`/plugins/${encodeURIComponent(name)}/references`),
};