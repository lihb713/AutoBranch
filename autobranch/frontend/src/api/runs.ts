import type { ReportResponse, RunDetail, RunOut, RunStart, RunState } from "../types/run";
import { request } from "./request";

async function requestReport(path: string): Promise<ReportResponse> {
  // 报告接口可能返回 JSON（执行中：{"status":"running"}）或纯文本 markdown（已完成）。
  // 按响应 content-type 分派，避免对 markdown 文本执行 JSON.parse 抛错。
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    throw new Error(`报告加载失败 (${res.status})`);
  }
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await res.json()) as ReportResponse;
  }
  return await res.text();
}

export const runsApi = {
  runTree: (id: number, inputs?: Record<string, unknown>) =>
    request<RunStart>(`/trees/${id}/run`, {
      method: "POST",
      body: JSON.stringify({ inputs }),
    }),

  listRuns: () => request<RunOut[]>("/runs"),

  getRunDetail: (runId: string | number) => request<RunDetail>(`/runs/${runId}`),

  retryRun: (runId: string | number) =>
    request<RunStart>(`/runs/${runId}/retry`, { method: "POST" }),

  deleteRun: (runId: string | number) =>
    request<void>(`/runs/${runId}`, { method: "DELETE" }),

  getRunState: (runId: string | number) => request<RunState>(`/runs/${runId}/state`),

  getRunReport: (runId: string | number) => requestReport(`/runs/${runId}/report`),

  getRunTrace: (runId: string | number) => requestReport(`/runs/${runId}/trace`),

  getReportFile: (path: string) => `/api/reports/${path}`,
};