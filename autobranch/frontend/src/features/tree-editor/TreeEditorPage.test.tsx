import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TreeEditorPage } from "./TreeEditorPage";

const mocks = vi.hoisted(() => ({
  listTrees: vi.fn(),
  getTree: vi.fn(),
  getTreeByName: vi.fn(),
  createDraft: vi.fn(),
  applyCommands: vi.fn(),
  saveTree: vi.fn(),
  deleteTree: vi.fn(),
  checkTree: vi.fn(),
  runTree: vi.fn(),
}));

vi.mock("../../api/trees", () => ({
  treesApi: {
    listTrees: mocks.listTrees,
    getTree: mocks.getTree,
    getTreeByName: mocks.getTreeByName,
    createDraft: mocks.createDraft,
    applyCommands: mocks.applyCommands,
    saveTree: mocks.saveTree,
    deleteTree: mocks.deleteTree,
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
  status: "published",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
  inputs: {},
  content: CONTENT,
};

function detail(overrides: Record<string, unknown> = {}) {
  return { ...TREE, ...overrides };
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
  mocks.listTrees.mockResolvedValue([]);
  mocks.getTree.mockResolvedValue(TREE);
  mocks.applyCommands.mockImplementation(async (_id: number, commands: unknown[]) => ({
    tree: detail(),
    created_node_id: (commands[0] as { op?: string }).op === "add_node" ? "n5" : null,
  }));
  mocks.saveTree.mockResolvedValue(detail());
  mocks.createDraft.mockResolvedValue({
    id: 9,
    name: "未命名-1",
    status: "draft",
    created_at: "x",
    updated_at: "x",
    inputs: {},
  });
});

describe("TreeEditorPage（后端权威编辑）", () => {
  it("加载既有文档：渲染画布节点", async () => {
    renderEditor("/editor/1");
    await waitFor(() => expect(screen.getByTestId("node-card-n1")).toBeInTheDocument());
    expect(screen.getByTestId("node-card-n3")).toBeInTheDocument();
    expect(screen.getByTestId("node-card-n4")).toBeInTheDocument();
  });

  it("选中节点展示字段", async () => {
    renderEditor("/editor/1");
    await waitFor(() => expect(screen.getByTestId("node-card-n3")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("node-card-n3"));
    expect(screen.getByTestId("node-type-badge")).toHaveTextContent("Step");
    expect(screen.getByTestId("field-n3-expect")).toHaveValue('出现"工作台"');
  });

  it("字段编辑通过 update_node 命令提交", async () => {
    renderEditor("/editor/1");
    await waitFor(() => expect(screen.getByTestId("node-card-n4")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("node-card-n4"));
    fireEvent.change(screen.getByTestId("field-n4-description"), {
      target: { value: "点击登录按钮" },
    });
    await waitFor(() => expect(mocks.applyCommands).toHaveBeenCalled());
    const commands = mocks.applyCommands.mock.calls[0][1];
    expect(commands[0]).toMatchObject({
      op: "update_node",
      node_id: "n4",
      patch: { description: "点击登录按钮" },
    });
  });

  it("保存调用 saveTree 并返回列表", async () => {
    renderEditor("/editor/1");
    await waitFor(() => expect(screen.getByTestId("node-card-n4")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(mocks.saveTree).toHaveBeenCalledWith(1, "冒烟流程"));
    expect(await screen.findByText("列表页占位")).toBeInTheDocument();
  });

  it("/editor 无 id：创建草稿并跳转", async () => {
    mocks.getTree.mockResolvedValue(detail({ id: 9, name: "未命名-1", status: "draft" }));
    renderEditor("/editor");
    await waitFor(() => expect(mocks.createDraft).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mocks.getTree).toHaveBeenCalledWith(9));
  });

  it("新增节点由后端 add_node 生成 id", async () => {
    renderEditor("/editor/1");
    await waitFor(() => expect(screen.getByTestId("node-card-n1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("side-tab-nodes"));
    fireEvent.click(screen.getByTestId("palette-Action"));
    await waitFor(() => expect(mocks.applyCommands).toHaveBeenCalled());
    expect(mocks.applyCommands.mock.calls[0][1][0]).toMatchObject({
      op: "add_node",
      node_type: "Action",
    });
  });

  it("删除节点提交 delete_node 命令", async () => {
    renderEditor("/editor/1");
    await waitFor(() => expect(screen.getByTestId("node-card-n4")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("node-card-n4"));
    fireEvent.click(screen.getByTestId("delete-node"));
    await waitFor(() => expect(mocks.applyCommands).toHaveBeenCalled());
    expect(mocks.applyCommands.mock.calls[0][1][0]).toMatchObject({
      op: "delete_node",
      node_id: "n4",
      subtree: false,
    });
  });

  it("ref 目标加载 typed outputs 并展示只读类型", async () => {
    const refContent = `tree: 引用流程
nodes:
  n1:
    type: Root
    body: n2
  n2:
    type: ref
    target: 文档B
    args: []
    returns:
      r_urlText: str
root: n1
`;
    mocks.getTree.mockResolvedValue(
      detail({ id: 2, name: "引用流程", content: refContent }),
    );
    mocks.listTrees.mockResolvedValue([{ ...TREE, name: "文档B" }]);
    mocks.getTreeByName.mockResolvedValue({
      id: 3,
      name: "文档B",
      status: "published",
      created_at: "x",
      updated_at: "x",
      inputs: {},
      content: "tree: 文档B\noutputs: {urlText: str}\nnodes:\n  n1: {type: Root, body: n2}\n  n2: {type: Action, description: x}\nroot: n1\n",
    });
    renderEditor("/editor/2");
    await waitFor(() => expect(screen.getByTestId("node-card-n2")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("node-card-n2"));
    await waitFor(() => expect(mocks.getTreeByName).toHaveBeenCalledWith("文档B"));
    expect(screen.getByTestId("ref-return-name-n2-0")).toHaveValue("r_urlText");
    expect(screen.getByTestId("ref-return-type-n2-0")).toHaveTextContent("str");
  });

  it("文档接口新增输入使用 ASCII 默认名并提交 update_doc", async () => {
    renderEditor("/editor/1");
    await waitFor(() => expect(screen.getByTestId("node-card-n1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("side-tab-tree"));
    fireEvent.click(screen.getByTestId("doc-input-add"));
    await waitFor(() => expect(mocks.applyCommands).toHaveBeenCalled());
    const cmd = mocks.applyCommands.mock.calls[0][1][0];
    expect(cmd.op).toBe("update_doc");
    expect(cmd.patch.inputs).toHaveProperty("input1");
  });

  it("草稿树不显示可执行按钮标题禁用", async () => {
    mocks.getTree.mockResolvedValue(detail({ status: "draft" }));
    renderEditor("/editor/1");
    await waitFor(() => expect(screen.getByRole("button", { name: "执行" })).toBeDisabled());
  });
});
