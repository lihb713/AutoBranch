import type { CheckIssue } from "../types/check";

const BASE = "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function extractMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .filter(
        (d): d is CheckIssue =>
          typeof d === "object" && d !== null && typeof (d as CheckIssue).message === "string",
      )
      .map((d) => d.message);
    return parts.length > 0 ? parts.join("\n") : fallback;
  }
  if (detail !== null && typeof detail === "object") {
    const inner = (detail as { detail?: unknown }).detail;
    if (inner !== undefined) {
      return extractMessage(inner, fallback);
    }
  }
  return fallback;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      detail = res.statusText;
    }
    const message = extractMessage(detail, res.statusText || `请求失败 (${res.status})`);
    throw new ApiError(res.status, message, detail);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}