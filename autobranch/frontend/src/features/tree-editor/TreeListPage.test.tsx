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
  createTree: vi.fn(),
  listTypes: vi.fn(),
}));

vi.mock("../../api/trees", () => ({
  treesApi: {
    listTrees: mocks.listTrees,
    getTree: vi.fn(),
    createTree: mocks.createTree,
    updateTree: vi.fn(),
    deleteTree: mocks.deleteTree,
    checkTree: vi.fn(),
  },
}));

vi.mock("../../api/runs", () => ({
  runsApi: { runTree: mocks.runTree, getReportFile: (p: string) => `/api/reports/${p}` },
}));

vi.mock("../../api/types", () => ({
  typesApi: { listTypes: mocks.listTypes },
}));

const TREES: TreeOut[] = [
  {
    id: 1,
    name: "登录流程",
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
    inputs: {},
  },
  {
    id: 2,
    name: "下单流程",
    created_at: "2026-01-02T00:00:00",
    updated_at: "2026-01-02T00:00:00",
    inputs: {},
  },
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
  mocks.listTypes.mockResolvedValue([
    { token: "str", constructible: true },
    { token: "int", constructible: true },
    { token: "float", constructible: true },
    { token: "bool", constructible: true },
    { token: "page_ref", constructible: false },
    { token: "object", constructible: false },
  ]);
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
      expect(mocks.runTree).toHaveBeenCalledWith(1, undefined);
    });
    expect(await screen.findByText("报告页占位")).toBeInTheDocument();
  });

  it("含可构造入参：弹入参对话框并提交", async () => {
    const withInputs: TreeOut = {
      id: 3,
      name: "带参流程",
      created_at: "2026-01-03T00:00:00",
      updated_at: "2026-01-03T00:00:00",
      inputs: { user: "str", n: "int" },
    };
    mocks.listTrees.mockResolvedValue([withInputs]);
    mocks.runTree.mockResolvedValue({ run_id: 55 });
    renderList();
    await screen.findByText("带参流程");

    fireEvent.click(screen.getByTestId("run-3"));
    expect(await screen.findByTestId("run-input-dialog")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("input-value-user"), { target: { value: "admin" } });
    fireEvent.change(screen.getByTestId("input-value-n"), { target: { value: "42" } });
    fireEvent.click(screen.getByTestId("run-dialog-confirm"));

    await waitFor(() => {
      expect(mocks.runTree).toHaveBeenCalledWith(3, { user: "admin", n: 42 });
    });
  });

  it("含不可构造入参：不渲染执行按钮", async () => {
    const withPageRef: TreeOut = {
      id: 4,
      name: "页签流程",
      created_at: "2026-01-04T00:00:00",
      updated_at: "2026-01-04T00:00:00",
      inputs: { 页: "page_ref" },
    };
    mocks.listTrees.mockResolvedValue([withPageRef]);
    renderList();
    await screen.findByText("页签流程");

    const row = screen.getByTestId("tree-row-4");
    const buttons = Array.from(row.querySelectorAll("button")).map((b) => b.textContent);
    expect(buttons).not.toContain("执行");
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

  it("导入文档：解析树名并 createTree，随后刷新列表", async () => {
    mocks.listTrees.mockResolvedValue([]);
    mocks.createTree.mockResolvedValue({ id: 9, name: "导入树", updated_at: "x" });
    renderList();
    await screen.findByText("还没有行为树");

    const content = `tree: 导入树
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: Action
    name: 操作
    description: 打开页面
root: n1
`;
    const file = new File([content], "tree.yaml", { type: "text/yaml" });
    fireEvent.change(screen.getByTestId("import-file"), { target: { files: [file] } });

    await waitFor(() => expect(mocks.createTree).toHaveBeenCalled());
    expect(mocks.createTree.mock.calls[0][0].name).toBe("导入树");
    expect(mocks.createTree.mock.calls[0][0].content).toContain("type: Root");
    expect(mocks.listTrees).toHaveBeenCalledTimes(2);
  });

  it("导入非法文档：显示错误且不 createTree", async () => {
    mocks.listTrees.mockResolvedValue([]);
    renderList();
    await screen.findByText("还没有行为树");

    const file = new File(["tree: 坏\nnodes: []"], "bad.yaml", { type: "text/yaml" });
    fireEvent.change(screen.getByTestId("import-file"), { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/导入失败/)).toBeInTheDocument();
    });
    expect(mocks.createTree).not.toHaveBeenCalled();
  });
});