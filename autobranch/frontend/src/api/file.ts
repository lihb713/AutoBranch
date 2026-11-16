import { request } from "./request";

const PREFIX = "/plugins/file";

export interface FileRecord {
  id: number;
  filename: string;
  path: string;
  size: number;
  content_type: string;
  created_at: string;
  updated_at: string;
}

export const fileApi = {
  list: () => request<FileRecord[]>(`${PREFIX}/files`),
  get: (id: number) => request<FileRecord>(`${PREFIX}/files/${id}`),
  upload: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch(`/api${PREFIX}/files`, { method: "POST", body: form });
    if (!resp.ok) throw new Error((await resp.text()) || "上传失败");
    return (await resp.json()) as FileRecord;
  },
  downloadUrl: (id: number) => `/api${PREFIX}/files/${id}/download`,
  delete: (id: number) =>
    request<{ ok: boolean }>(`${PREFIX}/files/${id}`, { method: "DELETE" }),
};
