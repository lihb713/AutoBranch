import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CheckReport } from "../../types/check";
import { TreeEditorPage } from "./TreeEditorPage";

const mocks = vi.hoisted(() => ({
  listTrees: vi.fn(),
  getTree: vi.fn(),
  getTreeByName: vi.fn(),
  createTree: vi.fn(),
  updateTree: vi.fn(),
  checkTree: vi.fn(),
  runTree: vi.fn(),
}));

vi.mock("../../api/trees", () => ({
  treesApi: {
    listTrees: mocks.listTrees,
    getTree: mocks.getTree,
    getTreeByName: mocks.getTreeByName,
    createTree: mocks.createTree,
    updateTree: mocks.updateTree,
    deleteTree: vi.fn(),
    checkTree: mocks.checkTree,
  },
}));

vi.mock("../../api/runs", () => ({
  runsApi: { runTree: mocks.runTree, getReportFile: (p: string) => `/api/reports/${p}` },
}));

const CONTENT = `tree: 冒烟流程
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: Sequence
    name: 主流程
    actions: [n3]
  n3:
    type: Step
    name: 登录
    action: n4
    expect: 出现"工作台"
  n4:
    type: Action
    name: 点登录
    description: 点击"登录"按钮
root: n1
`;

const TREE = {
  id: 1,
  name: "冒烟流程",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
  content: CONTENT,
};

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
  mocks.listTrees.mockResolvedValue([]);
});

describe("TreeEditorPage（统一槽位模型）", () => {
  it("加载既有文档：解析并渲染画布节点卡片", async () => {
    mocks.getTree.mockResolvedValue(TREE);
    renderEditor("/editor/1");

    expect(await screen.findByDisplayValue("冒烟流程")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("node-card-n1")).toBeInTheDocument();
    });
    expect(screen.getByTestId("node-card-n3")).toBeInTheDocument();
    expect(screen.getByTestId("node-card-n4")).toBeInTheDocument();
  });

  it("选中节点后在属性面板展示字段", async () => {
    mocks.getTree.mockResolvedValue(TREE);
    renderEditor("/editor/1");
    await waitFor(() => expect(screen.getByTestId("node-card-n3")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("node-card-n3"));
    expect(screen.getByTestId("node-type-badge")).toHaveTextContent("Step");
    expect(screen.getByTestId("field-n3-expect")).toHaveValue('出现"工作台"');
  });

  it("保存：先 /check 后 updateTree，内容为 serializeDoc 结果", async () => {
    mocks.getTree.mockResolvedValue(TREE);
    mocks.checkTree.mockResolvedValue({ ok: true, issues: [] } satisfies CheckReport);
    mocks.updateTree.mockResolvedValue({ id: 1, name: "冒烟流程", updated_at: "x" });
    renderEditor("/editor/1");
    await waitFor(() => expect(screen.getByTestId("node-card-n4")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("node-card-n4"));
    fireEvent.change(screen.getByTestId("field-n4-description"), {
      target: { value: "点击登录按钮" },
    });

    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(mocks.checkTree).toHaveBeenCalledWith(1));
    await waitFor(() => expect(mocks.updateTree).toHaveBeenCalled());
    expect(mocks.checkTree.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.updateTree.mock.invocationCallOrder[0],
    );
    const payload = mocks.updateTree.mock.calls[0][1];
    expect(payload.name).toBe("冒烟流程");
    expect(payload.content).toContain("点击登录按钮");
    expect(screen.getByText("列表页占位")).toBeInTheDocument();
  });

  it("即时校验不通过：展示错误清单且不发送保存请求", async () => {
    renderEditor("/editor");
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(screen.getByTestId("check-issues")).toBeInTheDocument();
    });
    expect(within(screen.getByTestId("check-issues")).getByText(/缺少必需槽位 body/)).toBeInTheDocument();
    expect(mocks.createTree).not.toHaveBeenCalled();
  });

  it("新建：点击面板创建 Step 并自动附 Action", async () => {
    renderEditor("/editor");
    await screen.findByTestId("palette-Step");
    fireEvent.click(screen.getByTestId("palette-Step"));

    expect(screen.getByTestId("node-card-n2")).toBeInTheDocument();
    expect(screen.getByTestId("node-type-n2")).toHaveTextContent("Step");
    expect(screen.getByTestId("node-card-n3")).toBeInTheDocument();
    expect(screen.getByTestId("node-type-n3")).toHaveTextContent("Action");
  });

  it("新建：构建合法文档后保存调用 createTree", async () => {
    mocks.createTree.mockResolvedValue({ id: 9, name: "新树", updated_at: "x" });
    renderEditor("/editor");

    fireEvent.change(screen.getByPlaceholderText("如：登录流程"), { target: { value: "新树" } });
    fireEvent.click(screen.getByTestId("palette-Step"));

    // 把 Step(n2) 挂到 Root(n1).body
    fireEvent.click(screen.getByTestId("node-card-n1"));
    fireEvent.change(screen.getByTestId("slot-n1-0"), { target: { value: "n2" } });

    // 补齐 Action(n3).description 与 Step(n2).expect
    fireEvent.click(screen.getByTestId("node-card-n3"));
    fireEvent.change(screen.getByTestId("field-n3-description"), {
      target: { value: "点击登录" },
    });
    fireEvent.click(screen.getByTestId("node-card-n2"));
    fireEvent.change(screen.getByTestId("field-n2-expect"), {
      target: { value: "出现工作台" },
    });

    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(mocks.createTree).toHaveBeenCalled());
    const payload = mocks.createTree.mock.calls[0][0];
    expect(payload.name).toBe("新树");
    expect(payload.content).toContain("type: Step");
    expect(payload.content).toContain("出现工作台");
    expect(screen.getByText("列表页占位")).toBeInTheDocument();
  });

  it("删除中间节点：其子节点回游离区（属性面板删除）", async () => {
    mocks.getTree.mockResolvedValue(TREE);
    renderEditor("/editor/1");
    await waitFor(() => expect(screen.getByTestId("node-card-n3")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("node-card-n3"));
    await waitFor(() => expect(screen.getByTestId("property-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("delete-node"));
    await waitFor(() => {
      expect(screen.queryByTestId("node-card-n3")).not.toBeInTheDocument();
    });
    // n4（原 n3 的子节点）回游离区
    expect(screen.getByTestId("free-tree-label-n4")).toHaveTextContent("游离");
  });

  it("根节点删除按钮禁用（属性面板）", async () => {
    mocks.getTree.mockResolvedValue(TREE);
    renderEditor("/editor/1");
    await waitFor(() => expect(screen.getByTestId("node-card-n1")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("node-card-n1"));
    await waitFor(() => expect(screen.getByTestId("delete-node")).toBeInTheDocument());
    expect(screen.getByTestId("delete-node")).toBeDisabled();
    expect(screen.getByTestId("delete-subtree")).toBeDisabled();
  });

  it("ref 展开后收缩：预览消失且按钮回到「展开」", async () => {
    const refContent = `tree: A
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: ref
    name: 去B
    target: B
    args: []
    returns: {}
root: n1
`;
    const refTree = {
      id: 7,
      name: "A",
      created_at: "2026-01-01T00:00:00",
      updated_at: "2026-01-01T00:00:00",
      content: refContent,
    };
    mocks.getTree.mockResolvedValue(refTree);
    mocks.getTreeByName.mockResolvedValue({
      id: 8,
      name: "B",
      created_at: "2026-01-01T00:00:00",
      updated_at: "2026-01-01T00:00:00",
      content: `tree: B
nodes:
  n1:
    type: Root
    name: B根
    body: n2
  n2:
    type: Action
    name: 动作
    description: x
root: n1
`,
    });
    renderEditor("/editor/1");
    await waitFor(() => expect(screen.getByTestId("node-card-n2")).toBeInTheDocument());

    // 展开 → 预览子树出现
    fireEvent.click(screen.getByTestId("node-toggle-n2"));
    await waitFor(() => expect(screen.getByTestId("preview-node-n1")).toBeInTheDocument());
    expect(screen.getByTestId("node-toggle-n2")).toHaveTextContent("收缩");

    // 收缩 → 预览消失、按钮回「展开」
    fireEvent.click(screen.getByTestId("node-toggle-n2"));
    await waitFor(() => {
      expect(screen.queryByTestId("preview-node-n1")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("node-toggle-n2")).toHaveTextContent("展开");
  });
});
