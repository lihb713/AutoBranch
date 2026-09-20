import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { RunOut } from "../../types/run";
import { RunListPage } from "./RunListPage";

const mocks = vi.hoisted(() => ({
  listRuns: vi.fn(),
  getRunDetail: vi.fn(),
  retryRun: vi.fn(),
  deleteRun: vi.fn(),
}));

vi.mock("../../api/runs", () => ({
  runsApi: {
    listRuns: mocks.listRuns,
    getRunDetail: mocks.getRunDetail,
    retryRun: mocks.retryRun,
    deleteRun: mocks.deleteRun,
    getReportFile: (p: string) => `/api/reports/${p}`,
  },
}));

const RUNS: RunOut[] = [
  {
    id: 1,
    tree_id: 1,
    tree_name: "冒烟流程",
    status: "success",
    inputs: { user: "admin" },
    outputs: { 结果: "ok" },
    tree_content_hash: "abcdef1234567890",
    failure_reason: null,
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:30",
    duration: 30,
    progress: null,
  },
  {
    id: 2,
    tree_id: 1,
    tree_name: "冒烟流程",
    status: "pending",
    inputs: {},
    outputs: null,
    tree_content_hash: "abcdef1234567890",
    failure_reason: null,
    created_at: "2026-01-02T00:00:00",
    updated_at: "2026-01-02T00:00:00",
    duration: null,
    progress: null,
  },
];

function renderList() {
  return render(
    <MemoryRouter initialEntries={["/runs"]}>
      <Routes>
        <Route path="/runs" element={<RunListPage />} />
        <Route path="/runs/:runId" element={<div>报告页占位</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listRuns.mockResolvedValue(RUNS);
  mocks.getRunDetail.mockResolvedValue({ ...RUNS[0], content_snapshot: "tree: 冒烟流程\nnodes: {}" });
  mocks.retryRun.mockResolvedValue({ run_id: 99 });
  mocks.deleteRun.mockResolvedValue(undefined);
  window.confirm = vi.fn(() => true);
});

describe("RunListPage", () => {
  it("渲染实例行（树名/状态/入参/耗时/指纹短显）", async () => {
    renderList();
    expect(await screen.findByTestId("run-row-1")).toBeInTheDocument();
    expect(screen.getAllByText("冒烟流程").length).toBe(2);
    expect(screen.getByText("排队中")).toBeInTheDocument();
    expect(screen.getByText(JSON.stringify({ user: "admin" }))).toBeInTheDocument();
    expect(screen.getByText("30s")).toBeInTheDocument();
    expect(screen.getAllByText("#abcdef1").length).toBe(2);
  });

  it("重试 → retryRun 并跳转新报告", async () => {
    renderList();
    await screen.findByTestId("run-row-1");
    fireEvent.click(screen.getByTestId("run-retry-1"));
    await waitFor(() => expect(mocks.retryRun).toHaveBeenCalledWith(1));
    expect(await screen.findByText("报告页占位")).toBeInTheDocument();
  });

  it("查看 → 跳转执行详情页", async () => {
    renderList();
    await screen.findByTestId("run-row-1");
    fireEvent.click(screen.getByTestId("run-view-1"));
    expect(await screen.findByText("报告页占位")).toBeInTheDocument();
  });

  it("删除 → 立即从列表移除并刷新", async () => {
    const remaining = RUNS.filter((r) => r.id !== 1);
    mocks.listRuns.mockResolvedValueOnce(RUNS).mockResolvedValue(remaining);
    renderList();
    await screen.findByTestId("run-row-1");
    fireEvent.click(screen.getByTestId("run-delete-1"));
    await waitFor(() => expect(mocks.deleteRun).toHaveBeenCalledWith(1));
    await waitFor(() => expect(screen.queryByTestId("run-row-1")).not.toBeInTheDocument());
    expect(mocks.listRuns.mock.calls.length).toBeGreaterThanOrEqual(2); // 乐观移除 + load() 刷新
  });

  it("删除 → 确认后 deleteRun", async () => {
    renderList();
    await screen.findByTestId("run-row-1");
    fireEvent.click(screen.getByTestId("run-delete-1"));
    await waitFor(() => expect(mocks.deleteRun).toHaveBeenCalledWith(1));
    expect(window.confirm).toHaveBeenCalled();
  });

  it("存在进行中实例时持续轮询（listRuns 多次调用）", async () => {
    mocks.listRuns
      .mockResolvedValueOnce([RUNS[1]]) // pending → 继续轮询
      .mockResolvedValue([]); // 结束后停
    renderList();
    await waitFor(
      () => expect(mocks.listRuns.mock.calls.length).toBeGreaterThanOrEqual(2),
      { timeout: 4000 },
    );
  });
});