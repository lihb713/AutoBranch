import { afterEach, describe, expect, it, vi } from "vitest";
import { treesApi } from "./trees";

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    json: () => Promise.resolve(body),
  } as Response;
}

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("treesApi 请求方法与路径", () => {
  it("listTrees → GET /api/trees", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);
    await treesApi.listTrees();
    expect(fetchMock).toHaveBeenCalledWith("/api/trees", expect.anything());
    const [url, init] = fetchMock.mock.calls[0];
    expect((init as RequestInit).method ?? "GET").toBe("GET");
    expect(url).toBe("/api/trees");
  });

  it("getTree → GET /api/trees/7", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 7, content: "x" }));
    vi.stubGlobal("fetch", fetchMock);
    await treesApi.getTree(7);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/trees/7");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  it("getTreeByName → GET /api/trees/by-name/登录（url 编码）", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 5, name: "登录", content: "x" }));
    vi.stubGlobal("fetch", fetchMock);
    await treesApi.getTreeByName("登录");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/trees/by-name/%E7%99%BB%E5%BD%95");
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  it("createTree → POST /api/trees 带 body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, name: "登录" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    await treesApi.createTree({ name: "登录", content: "Step:" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/trees");
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      name: "登录",
      content: "Step:",
    });
  });

  it("updateTree → PUT /api/trees/3", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 3, name: "n" }));
    vi.stubGlobal("fetch", fetchMock);
    await treesApi.updateTree(3, { content: "new" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/trees/3");
    expect((init as RequestInit).method).toBe("PUT");
  });

  it("deleteTree → DELETE /api/trees/3", async () => {
    fetchMock.mockResolvedValue(jsonResponse(null, 204));
    vi.stubGlobal("fetch", fetchMock);
    await treesApi.deleteTree(3);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/trees/3");
    expect((init as RequestInit).method).toBe("DELETE");
  });

  it("checkTree → POST /api/trees/3/check", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: false, issues: [] }));
    vi.stubGlobal("fetch", fetchMock);
    await treesApi.checkTree(3);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/trees/3/check");
    expect((init as RequestInit).method).toBe("POST");
  });
});