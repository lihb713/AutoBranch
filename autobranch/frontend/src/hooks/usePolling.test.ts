import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePolling } from "./usePolling";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("usePolling", () => {
  it("首次立即执行并按间隔 tick", async () => {
    const fetcher = vi.fn().mockResolvedValue({ n: 1 });
    const { result } = renderHook(() =>
      usePolling(fetcher, () => false),
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(result.current.data).toEqual({ n: 1 });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("shouldStop 为真时停止后续请求", async () => {
    let completed = false;
    const fetcher = vi
      .fn()
      .mockImplementation(() => Promise.resolve({ finished: completed }));
    const { result } = renderHook(() =>
      usePolling(fetcher, (s: { finished: boolean }) => s.finished),
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(result.current.data).toEqual({ finished: false });

    completed = true;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(result.current.data).toEqual({ finished: true });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("卸载后不再请求（清理 timer）", async () => {
    const fetcher = vi.fn().mockResolvedValue({ n: 1 });
    const { unmount } = renderHook(() => usePolling(fetcher, () => false));

    await act(async () => {
      await Promise.resolve();
    });
    expect(fetcher).toHaveBeenCalledTimes(1);

    unmount();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("卸载后 in-flight 请求完成不回写状态（cancelled 标志）", async () => {
    let resolveFn: (v: { n: number }) => void = () => {};
    const fetcher = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFn = resolve;
        }),
    );
    const { unmount } = renderHook(() => usePolling(fetcher, () => false));

    await act(async () => {
      await Promise.resolve();
    });
    unmount();

    await act(async () => {
      resolveFn({ n: 9 });
      await Promise.resolve();
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("请求失败设置 error 且不再轮询", async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new Error("网络错误"))
      .mockResolvedValue({ n: 2 });
    const { result } = renderHook(() => usePolling(fetcher, () => false));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toBe("网络错误");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});