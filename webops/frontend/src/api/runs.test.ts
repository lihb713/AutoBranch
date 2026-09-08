import { afterEach, describe, expect, it, vi } from "vitest";
import { runsApi } from "./runs";

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    headers: new Headers({ "content-type": "application/json" }),
    json: () => Promise.resolve(body),
  } as Response;
}

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("runsApi 请求方法与路径", () => {
  it("runTree → POST /api/trees/3/run", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ run_id: 5 }, 202));
    vi.stubGlobal("fetch", fetchMock);
    const result = await runsApi.runTree(3);
    expect(result.run_id).toBe(5);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/trees/3/run");
    expect((init as RequestInit).method).toBe("POST");
  });

  it("getRunState → GET /api/runs/5/state", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ run_id: "5", progress: 0.5, finished: false }));
    vi.stubGlobal("fetch", fetchMock);
    await runsApi.getRunState("5");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/runs/5/state");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  it("getRunReport → GET /api/runs/5/report", async () => {
    fetchMock.mockResolvedValue(jsonResponse("# 报告"));
    vi.stubGlobal("fetch", fetchMock);
    await runsApi.getRunReport(5);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/runs/5/report");
  });

  it("getRunTrace → GET /api/runs/5/trace", async () => {
    fetchMock.mockResolvedValue(jsonResponse("# 回溯"));
    vi.stubGlobal("fetch", fetchMock);
    await runsApi.getRunTrace("5");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/runs/5/trace");
  });

  it("getReportFile 返回可访问 URL", () => {
    expect(runsApi.getReportFile("1/shot.png")).toBe("/api/reports/1/shot.png");
  });
});

describe("requestReport 图片/文本响应分流", () => {
  it("文本 markdown 响应返回文本", async () => {
    const text = "# 执行报告\n节点1 SUCCESS";
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "text/markdown; charset=utf-8" }),
      json: () => Promise.reject(new Error("should not call json")),
      text: () => Promise.resolve(text),
    } as unknown as Response);
    vi.stubGlobal("fetch", fetchMock);
    const result = await runsApi.getRunReport(5);
    expect(result).toBe(text);
  });

  it("JSON running 响应返回对象", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: () => Promise.resolve({ run_id: "5", status: "running" }),
    } as unknown as Response);
    vi.stubGlobal("fetch", fetchMock);
    const result = await runsApi.getRunTrace("5");
    expect(result).toEqual({ run_id: "5", status: "running" });
  });

  it("非 2xx 状态抛出错误", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 404,
      headers: new Headers({ "content-type": "application/json" }),
    } as unknown as Response);
    vi.stubGlobal("fetch", fetchMock);
    await expect(runsApi.getRunReport(5)).rejects.toThrow("报告加载失败");
  });
});