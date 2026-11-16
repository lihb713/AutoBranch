import type {
  ConfigSchemaItem,
  FunctionInfo,
  PluginCheckOut,
  PluginCreate,
  PluginDeleteOut,
  PluginDetailOut,
  PluginManifestOut,
  PluginOut,
  PluginUpdate,
} from "../types/plugin";
import { request } from "./request";

export const pluginsApi = {
  listPlugins: (includeManifest = false) =>
    request<PluginOut[]>(
      `/plugins${includeManifest ? "?include_manifest=true" : ""}`,
    ),

  listFunctions: () => request<FunctionInfo[]>("/functions"),

  getPlugin: (name: string) =>
    request<PluginDetailOut>(`/plugins/${encodeURIComponent(name)}`),

  getManifest: (name: string) =>
    request<PluginManifestOut>(`/plugins/${encodeURIComponent(name)}/manifest`),

  getConfig: (name: string) =>
    request<Record<string, unknown>>(`/plugins/${encodeURIComponent(name)}/config`),

  updateConfig: (name: string, config: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/plugins/${encodeURIComponent(name)}/config`, {
      method: "PUT",
      body: JSON.stringify(config),
    }),

  listPluginFunctions: (name: string) =>
    request<FunctionInfo[]>(`/plugins/${encodeURIComponent(name)}/functions`),

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

export type { ConfigSchemaItem };
