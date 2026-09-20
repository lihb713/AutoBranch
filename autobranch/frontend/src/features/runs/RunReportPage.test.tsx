import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RunState } from "../../types/run";
import { RunReportPage } from "./RunReportPage";

const mocks = vi.hoisted(() => ({
  getRunState: vi.fn(),
  getRunReport: vi.fn(),
  getRunTrace: vi.fn(),
  getRunDetail: vi.fn(),
  retryRun: vi.fn(),
}));

vi.mock("../../api/runs", () => ({
  runsApi: {
    getRunState: mocks.getRunState,
    getRunReport: mocks.getRunReport,
    getRunTrace: mocks.getRunTrace,
    getRunDetail: mocks.getRunDetail,
    retryRun: mocks.retryRun,
    getReportFile: (p: string) => `/api/reports/${p}`,
  },
}));

const RUNNING: RunState = {
  run_id: "5",
  progress: 0.33,
  current_node: { node_type: "Step", node_desc: "点\"登录\"" },
  completed: [{ node_type: "Step", node_desc: "打开页面", result: "success", timestamp: "t1", action_call: null, condition_result: null, page_url: null, screenshot_path: null }],
  finished: false,
  failure_reason: null,
};

const MIDDLE: RunState = {
  ...RUNNING,
  progress: 0.66,
  current_node: { node_type: "Condition", node_desc: "出现\"工作台\"" },
  completed: [
    ...RUNNING.completed,
    { node_type: "Condition", node_desc: "出现\"工作台\"", result: "failure", timestamp: "t2", action_call: null, condition_result: false, page_url: "https://x", screenshot_path: "5/shot.png" },
  ],
};

const FINISHED: RunState = {
  ...RUNNING,
  progress: 1.0,
  current_node: null,
  completed: [
    ...MIDDLE.completed,
    { node_type: "Step", node_desc: "点\"退出\"", result: "success", timestamp: "t3", action_call: null, condition_result: null, page_url: null, screenshot_path: null },
  ],
  finished: true,
};

function renderReport() {
  return render(
    <MemoryRouter initialEntries={["/runs/5"]}>
      <Routes>
        <Route path="/runs/:runId" element={<RunReportPage />} />
        <Route path="/" element={<div>列表页占位</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  mocks.getRunDetail.mockResolvedValue({
    id: 5,
    tree_id: 1,
    tree_name: "冒烟流程",
    status: "success",
    inputs: {},
    outputs: null,
    tree_content_hash: "abc123",
    failure_reason: null,
    created_at: null,
    updated_at: null,
    duration: null,
    progress: null,
    content_snapshot: "tree: 冒烟流程",
  });
  mocks.retryRun.mockResolvedValue({ run_id: 99 });
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("RunReportPage 轮询渲染", () => {
  it("状态序列驱动进度/着色实时更新，finished 后停止轮询并加载两类报告", async () => {
    const seq = [RUNNING, MIDDLE, FINISHED];
    mocks.getRunState.mockImplementation(() => Promise.resolve(seq.shift() ?? FINISHED));
    mocks.getRunReport.mockResolvedValue("# 执行报告");
    mocks.getRunTrace.mockResolvedValue("# 回溯报告");

    renderReport();

    await act(async () => {
      await Promise.resolve();
    });
    expect(mocks.getRunState).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("progress-text").textContent).toContain("33%");
    expect(screen.getByTestId("current-node")).toBeInTheDocument();
    expect(screen.getByTestId("report-node-Step").dataset.result).toBe("success");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(mocks.getRunState).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("progress-text").textContent).toContain("66%");
    const failedNode = screen.getByTestId("report-node-Condition");
    expect(failedNode.dataset.result).toBe("failure");
    expect(failedNode.className).toContain("node-failure");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(mocks.getRunState).toHaveBeenCalledTimes(3);
    expect(screen.getByTestId("progress-text").textContent).toContain("100%");
    expect(screen.getByTestId("report-panel")).toBeInTheDocument();

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mocks.getRunReport).toHaveBeenCalledWith("5");
    expect(mocks.getRunTrace).toHaveBeenCalledWith("5");
    expect(screen.getByText("# 执行报告")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(mocks.getRunState).toHaveBeenCalledTimes(3);
  });

  it("报告与回溯视图切换", async () => {
    const seq = [RUNNING, MIDDLE, FINISHED];
    mocks.getRunState.mockImplementation(() => Promise.resolve(seq.shift() ?? FINISHED));
    mocks.getRunReport.mockResolvedValue("执行报告文本");
    mocks.getRunTrace.mockResolvedValue("回溯报告文本");

    renderReport();
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText("执行报告文本")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "回溯报告" }));
    expect(screen.getByText("回溯报告文本")).toBeInTheDocument();
  });

  it("轮询失败：显示提示并保持已渲染状态", async () => {
    mocks.getRunState
      .mockResolvedValueOnce(RUNNING)
      .mockRejectedValueOnce(new Error("网络错误"));
    mocks.getRunReport.mockResolvedValue("x");
    mocks.getRunTrace.mockResolvedValue("x");

    renderReport();
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByTestId("progress-text").textContent).toContain("33%");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(screen.getByText(/轮询失败：网络错误/)).toBeInTheDocument();
    expect(screen.getByTestId("progress-text").textContent).toContain("33%");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(mocks.getRunState).toHaveBeenCalledTimes(2);
  });

  it("失败原因渲染", async () => {
    const failed = { ...FINISHED, failure_reason: "LLM 超时" };
    mocks.getRunState.mockResolvedValue(failed);
    mocks.getRunReport.mockResolvedValue("报告");
    mocks.getRunTrace.mockResolvedValue("回溯");

    renderReport();
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("执行失败：LLM 超时")).toBeInTheDocument();
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByTestId("report-panel")).toBeInTheDocument();
  });
});