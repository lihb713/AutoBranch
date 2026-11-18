import { request } from "./request";

const PREFIX = "/plugins/file";

export interface FileRecord {
  id: number;
  filename: string;
  path: string;
  size: number;
  content_type: string;
  md5: string;
  created_at: string;
  updated_at: string;
}

export interface FileDirectory {
  id: number;
  path: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface FileEntries {
  path: string;
  directories: FileDirectory[];
  files: FileRecord[];
}

async function uploadFile(file: File, path: string) {
  const form = new FormData();
  form.append("file", file);
  form.append("path", path);
  const resp = await fetch(`/api${PREFIX}/files`, { method: "POST", body: form });
  if (!resp.ok) throw new Error((await resp.text()) || "上传失败");
  return (await resp.json()) as FileRecord;
}

export const fileApi = {
  list: () => request<FileRecord[]>(`${PREFIX}/files`),
  listEntries: (path = "") =>
    request<FileEntries>(`${PREFIX}/entries?path=${encodeURIComponent(path)}`),
  listDirectories: () => request<FileDirectory[]>(`${PREFIX}/directories`),
  get: (id: number) => request<FileRecord>(`${PREFIX}/files/${id}`),
  upload: (file: File, path = "") => uploadFile(file, path),
  createDirectory: (path: string) =>
    request<FileDirectory>(`${PREFIX}/directories`, {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  renameDirectory: (id: number, path: string) =>
    request<FileDirectory>(`${PREFIX}/directories/${id}`, {
      method: "PUT",
      body: JSON.stringify({ path }),
    }),
  deleteDirectory: (id: number, recursive = true) =>
    request<{ ok: boolean }>(`${PREFIX}/directories/${id}?recursive=${recursive}`, {
      method: "DELETE",
    }),
  downloadUrl: (id: number) => `/api${PREFIX}/files/${id}/download`,
  downloadPathUrl: (path: string) =>
    `/api${PREFIX}/download?path=${encodeURIComponent(path)}`,
  delete: (id: number) =>
    request<{ ok: boolean }>(`${PREFIX}/files/${id}`, { method: "DELETE" }),
};
