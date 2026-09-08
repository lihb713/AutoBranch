import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, request } from "./request";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 404 ? "Not Found" : "Error",
    json: () => Promise.resolve(body),
  } as Response;
}

const fetchMock = vi.fn();

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("request 封装", () => {
  it("成功分支：GET 返回解析后的 JSON", async () => {
    const body = [{ id: 1, name: "登录流程" }];
    fetchMock.mockResolvedValue(jsonResponse(body));
    vi.stubGlobal("fetch", fetchMock);

    const result = await request<unknown[]>("/trees");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/trees",
      expect.objectContaining({ headers: { "Content-Type": "application/json" } }),
    );
    expect(result).toEqual(body);
  });

  it("成功分支：204 无 body 返回 undefined", async () => {
    fetchMock.mockResolvedValue(jsonResponse(null, 204));
    vi.stubGlobal("fetch", fetchMock);

    const result = await request<void>("/trees/1", { method: "DELETE" });

    expect(result).toBeUndefined();
  });

  it("失败分支：非 2xx 抛 ApiError 且提取字符串 detail", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "tree not found" }, 404));
    vi.stubGlobal("fetch", fetchMock);

    await expect(request("/trees/999")).rejects.toMatchObject({
      status: 404,
      message: "tree not found",
      name: "ApiError",
    });
  });

  it("失败分支：422 detail 为错误清单时合并 message", async () => {
    const detail = [
      { code: "structure", message: "Step 缺少必需字段 'action'", rule: "结构合法性", loc: "x" },
      { code: "verify", message: "Step 缺少验证条件 'expect'", rule: "验证条件", loc: "x" },
    ];
    fetchMock.mockResolvedValue(jsonResponse({ detail }, 422));
    vi.stubGlobal("fetch", fetchMock);

    const err = await request("/trees").catch((e: unknown) => e) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.message).toContain("Step 缺少必需字段 'action'");
    expect(err.message).toContain("Step 缺少验证条件 'expect'");
  });
});