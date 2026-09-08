import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/request";
import type { TreeOut } from "../../types/tree";
import { TreeListPage } from "./TreeListPage";

const mocks = vi.hoisted(() => ({
  listTrees: vi.fn(),
  deleteTree: vi.fn(),
  runTree: vi.fn(),
}));

vi.mock("../../api/trees", () => ({
  treesApi: {
    listTrees: mocks.listTrees,
    getTree: vi.fn(),
    createTree: vi.fn(),
    updateTree: vi.fn(),
    deleteTree: mocks.deleteTree,
    checkTree: vi.fn(),
  },
}));

vi.mock("../../api/runs", () => ({
  runsApi: { runTree: mocks.runTree, getReportFile: (p: string) => `/api/reports/${p}` },
}));

const TREES: TreeOut[] = [
  { id: 1, name: "登录流程", created_at: "2026-01-01T00:00:00", updated_at: "2026-01-01T00:00:00" },
  { id: 2, name: "下单流程", created_at: "2026-01-02T00:00:00", updated_at: "2026-01-02T00:00:00" },
];

function renderList() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<TreeListPage />} />
        <Route path="/editor/:id?" element={<div>编辑器占位</div>} />
        <Route path="/runs/:runId" element={<div>报告页占位</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("TreeListPage", () => {
  it("渲染列表（名称与更新时间）", async () => {
    mocks.listTrees.mockResolvedValue(TREES);
    renderList();
    await waitFor(() => {
      expect(screen.getByText("登录流程")).toBeInTheDocument();
    });
    expect(screen.getByText("下单流程")).toBeInTheDocument();
    expect(screen.getByText("登录流程").closest("tr")).toBeInTheDocument();
  });

  it("空列表显示空状态", async () => {
    mocks.listTrees.mockResolvedValue([]);
    renderList();
    expect(await screen.findByText("还没有行为树")).toBeInTheDocument();
  });

  it("删除成功移除该行", async () => {
    mocks.listTrees.mockResolvedValue(TREES);
    mocks.deleteTree.mockResolvedValue(undefined);
    renderList();
    await screen.findByText("登录流程");

    const row = screen.getByTestId("tree-row-1");
    const buttons = row.querySelectorAll("button");
    const deleteBtn = Array.from(buttons).find((b) => b.textContent === "删除") as HTMLElement;
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(mocks.deleteTree).toHaveBeenCalledWith(1);
    });
    await waitFor(() => {
      expect(screen.queryByText("登录流程")).not.toBeInTheDocument();
    });
    expect(screen.getByText("下单流程")).toBeInTheDocument();
  });

  it("删除 404 → 提示错误并刷新列表", async () => {
    mocks.listTrees.mockResolvedValue(TREES);
    mocks.deleteTree.mockRejectedValue(new ApiError(404, "行为树不存在 (id=1)", { detail: "x" }));
    renderList();
    await screen.findByText("登录流程");

    const row = screen.getByTestId("tree-row-1");
    const deleteBtn = Array.from(row.querySelectorAll("button")).find(
      (b) => b.textContent === "删除",
    ) as HTMLElement;
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByText("行为树「登录流程」不存在，列表已刷新")).toBeInTheDocument();
    });
    expect(mocks.listTrees).toHaveBeenCalledTimes(2);
  });

  it("点击行跳转编辑器", async () => {
    mocks.listTrees.mockResolvedValue(TREES);
    renderList();
    await screen.findByText("登录流程");
    fireEvent.click(screen.getByText("登录流程"));
    expect(await screen.findByText("编辑器占位")).toBeInTheDocument();
  });

  it("执行触发 runTree → 跳转报告页", async () => {
    mocks.listTrees.mockResolvedValue(TREES);
    mocks.runTree.mockResolvedValue({ run_id: 42 });
    renderList();
    await screen.findByText("登录流程");

    const row = screen.getByTestId("tree-row-1");
    const runBtn = Array.from(row.querySelectorAll("button")).find(
      (b) => b.textContent === "执行",
    ) as HTMLElement;
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(mocks.runTree).toHaveBeenCalledWith(1);
    });
    expect(await screen.findByText("报告页占位")).toBeInTheDocument();
  });

  it("执行触发 409 给出错误提示", async () => {
    mocks.listTrees.mockResolvedValue(TREES);
    mocks.runTree.mockRejectedValue(new ApiError(409, "该行为树已有进行中的执行", { detail: "x" }));
    renderList();
    await screen.findByText("登录流程");

    const row = screen.getByTestId("tree-row-1");
    const runBtn = Array.from(row.querySelectorAll("button")).find(
      (b) => b.textContent === "执行",
    ) as HTMLElement;
    fireEvent.click(runBtn);

    expect(
      await screen.findByText("该行为树已有进行中的执行"),
    ).toBeInTheDocument();
  });
});