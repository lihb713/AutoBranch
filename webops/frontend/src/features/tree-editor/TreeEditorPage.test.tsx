import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/request";
import type { CheckReport } from "../../types/check";
import { TreeEditorPage } from "./TreeEditorPage";

const mocks = vi.hoisted(() => ({
  getTree: vi.fn(),
  createTree: vi.fn(),
  updateTree: vi.fn(),
  deleteTree: vi.fn(),
  checkTree: vi.fn(),
  runTree: vi.fn(),
}));

vi.mock("../../api/trees", () => ({
  treesApi: {
    listTrees: vi.fn(),
    getTree: mocks.getTree,
    createTree: mocks.createTree,
    updateTree: mocks.updateTree,
    deleteTree: mocks.deleteTree,
    checkTree: mocks.checkTree,
  },
}));

vi.mock("../../api/runs", () => ({
  runsApi: { runTree: mocks.runTree, getReportFile: (p: string) => `/api/reports/${p}` },
}));

const CONTENT = `Sequence:
  - Step:
      action: 点"登录"
      expect: 出现"工作台"
`;

const TREE = {
  id: 1,
  name: "冒烟流程",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
  content: CONTENT,
};

function fakeDataTransfer(): DataTransfer {
  const store = new Map<string, string>();
  return {
    setData: (k: string, v: string) => store.set(k, v),
    getData: (k: string) => store.get(k) ?? "",
    effectAllowed: "",
    dropEffect: "none",
  } as unknown as DataTransfer;
}

function renderEditor(route = "/editor/1") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/editor/:id?" element={<TreeEditorPage />} />
        <Route path="/" element={<div>列表页占位</div>} />
        <Route path="/runs/:runId" element={<div>报告页占位</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("TreeEditorPage", () => {
  it("加载既有树：getTree → 解析进编辑器并渲染字段", async () => {
    mocks.getTree.mockResolvedValue(TREE);
    renderEditor("/editor/1");

    await waitFor(() => {
      expect(screen.getByDisplayValue("冒烟流程")).toBeInTheDocument();
    });
    expect(screen.getByDisplayValue('点"登录"')).toBeInTheDocument();
    expect(screen.getByText("Step")).toBeInTheDocument();
    expect(screen.getByText("Sequence")).toBeInTheDocument();
  });

  it("校验通过：先 checkTree 后 updateTree，保存成功回列表", async () => {
    mocks.getTree.mockResolvedValue(TREE);
    mocks.checkTree.mockResolvedValue({ ok: true, issues: [] } satisfies CheckReport);
    mocks.updateTree.mockResolvedValue({ id: 1, name: "冒烟流程", updated_at: "x" });
    renderEditor("/editor/1");

    await waitFor(() => {
      expect(screen.getByDisplayValue('点"登录"')).toBeInTheDocument();
    });
    fireEvent.change(screen.getByDisplayValue('点"登录"'), {
      target: { value: '点"登录按钮"' },
    });

    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(mocks.checkTree).toHaveBeenCalledWith(1);
    });
    await waitFor(() => {
      expect(mocks.updateTree).toHaveBeenCalled();
    });
    expect(mocks.checkTree.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.updateTree.mock.invocationCallOrder[0],
    );
    const payload = mocks.updateTree.mock.calls[0][1];
    expect(payload.name).toBe("冒烟流程");
    expect(payload.content).toContain('点"登录按钮"');
    expect(screen.getByText("列表页占位")).toBeInTheDocument();
  });

  it("校验失败：展示错误清单且不发送保存请求", async () => {
    mocks.getTree.mockResolvedValue(TREE);
    mocks.checkTree.mockResolvedValue({
      ok: false,
      issues: [{ code: "verify.missing_condition", message: "Step 缺少验证条件 'expect'", rule: "验证条件", loc: null }],
    } satisfies CheckReport);
    renderEditor("/editor/1");

    await waitFor(() => {
      expect(screen.getByDisplayValue('点"登录"')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(screen.getByTestId("check-issues")).toBeInTheDocument();
    });
    expect(screen.getByText("Step 缺少验证条件 'expect'")).toBeInTheDocument();
    expect(mocks.updateTree).not.toHaveBeenCalled();
    expect(screen.queryByText("列表页占位")).not.toBeInTheDocument();
  });

  it("新建：画布为空时保存给出提示", async () => {
    renderEditor("/editor");
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByText("画布为空：请先从左侧面板拖拽节点构建行为树")).toBeInTheDocument();
  });

  it("新建：创建接口 422 校验失败 → 渲染错误清单", async () => {
    mocks.createTree.mockRejectedValue(
      new ApiError(422, "校验失败", [
        { code: "structure.missing_field", message: "Step 缺少必需字段 'action'", rule: "结构合法性", loc: null },
      ]),
    );
    renderEditor("/editor");

    fireEvent.change(screen.getByPlaceholderText("如：登录流程"), { target: { value: "新树" } });
    const dt = fakeDataTransfer();
    fireEvent.dragStart(screen.getByTestId("palette-Step"), { dataTransfer: dt });
    fireEvent.drop(screen.getByTestId("canvas-drop-root"), { dataTransfer: dt });

    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(screen.getByTestId("check-issues")).toBeInTheDocument();
    });
    expect(screen.getByText("Step 缺少必需字段 'action'")).toBeInTheDocument();
    expect(mocks.createTree).toHaveBeenCalled();
    expect(screen.queryByText("列表页占位")).not.toBeInTheDocument();
  });

  it("拖拽：从面板拖节点入画布成为根节点", async () => {
    renderEditor("/editor");
    const dt = fakeDataTransfer();
    fireEvent.dragStart(screen.getByTestId("palette-Step"), { dataTransfer: dt });
    fireEvent.drop(screen.getByTestId("canvas-drop-root"), { dataTransfer: dt });
    expect(screen.getByText("Step")).toBeInTheDocument();
  });

  it("拖拽：把 Step 拖入 Sequence 节点内添加子节点", async () => {
    renderEditor("/editor");
    const dt = fakeDataTransfer();
    fireEvent.dragStart(screen.getByTestId("palette-Sequence"), { dataTransfer: dt });
    fireEvent.drop(screen.getByTestId("canvas-drop-root"), { dataTransfer: dt });
    expect(screen.getByText("Sequence")).toBeInTheDocument();

    const dt2 = fakeDataTransfer();
    fireEvent.dragStart(screen.getByTestId("palette-Step"), { dataTransfer: dt2 });
    const seqCard = screen.getByText("Sequence").closest(".tree-node") as HTMLElement;
    fireEvent.drop(seqCard, { dataTransfer: dt2 });

    await waitFor(() => {
      expect(seqCard.querySelectorAll('[data-testid^="node-"]')).toHaveLength(1);
    });
    const childId = seqCard.querySelector(".tree-node__children > .tree-node")?.getAttribute("data-testid");
    expect(childId).toBeTruthy();
    expect(seqCard.querySelector(".tree-node__children")?.textContent).toContain("Step");
  });
});