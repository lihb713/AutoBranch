import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TreeCanvas } from "./TreeCanvas";
import type { TreeDoc } from "./treeModel";

const DOC: TreeDoc = {
  tree: "x",
  inputs: {},
  outputs: [],
  config: {},
  root: "n1",
  nodes: {
    n1: { id: "n1", type: "Root", name: "根", fields: {}, body: "n2" },
    n2: { id: "n2", type: "Sequence", name: "主流程", fields: {}, actions: ["n3"] },
    n3: { id: "n3", type: "Step", name: "登录", fields: { expect: "ok" }, action: "n4" },
    n4: { id: "n4", type: "Action", name: "点登录", fields: { description: "点" } },
    f1: { id: "f1", type: "Action", name: "游离操作", fields: { description: "x" } },
  },
};

function renderCanvas(props: Partial<Parameters<typeof TreeCanvas>[0]> = {}) {
  return render(
    <TreeCanvas
      doc={DOC}
      selectedId={null}
      issueByNode={new Map()}
      onSelect={() => {}}
      {...props}
    />,
  );
}

describe("TreeCanvas", () => {
  it("渲染全部节点卡片", () => {
    renderCanvas();
    for (const id of ["n1", "n2", "n3", "n4", "f1"]) {
      expect(screen.getByTestId(`node-card-${id}`)).toBeInTheDocument();
    }
  });

  it("用 SVG path 绘制父子连线（主树 3 条）", () => {
    const { container } = renderCanvas();
    expect(container.querySelectorAll("svg path")).toHaveLength(3);
    expect(container.querySelectorAll('[data-testid="tree-edge"]')).toHaveLength(3);
  });

  it("游离树带根 name 与「游离」标记", () => {
    renderCanvas();
    const label = screen.getByTestId("free-tree-label-f1");
    expect(label).toHaveTextContent("游离操作");
    expect(label).toHaveTextContent("游离");
  });

  it("选中节点加高亮类", () => {
    renderCanvas({ selectedId: "n2" });
    expect(screen.getByTestId("node-card-n2").className).toContain("node-card--selected");
    expect(screen.getByTestId("node-card-n1").className).not.toContain("node-card--selected");
  });

  it("点击节点回调 onSelect", () => {
    const onSelect = vi.fn();
    renderCanvas({ onSelect });
    fireEvent.click(screen.getByTestId("node-card-n3"));
    expect(onSelect).toHaveBeenCalledWith("n3");
  });

  it("ref 展开显示被引文档只读子树（含内部连线与连接主树的线）", () => {
    const docWithRef: TreeDoc = {
      tree: "A",
      inputs: {},
      outputs: [],
      config: {},
      root: "r1",
      nodes: {
        r1: { id: "r1", type: "Root", name: "根", fields: {}, body: "r2" },
        r2: {
          id: "r2",
          type: "ref",
          name: "去B",
          fields: {},
          target: "B",
          args: [],
          returns: {},
        },
      },
    };
    const preview: TreeDoc = {
      tree: "B",
      inputs: {},
      outputs: [],
      config: {},
      root: "b1",
      nodes: {
        b1: { id: "b1", type: "Root", name: "B根", fields: {}, body: "b2" },
        b2: { id: "b2", type: "Action", name: "动作", fields: { description: "x" } },
      },
    };
    const onToggleRef = vi.fn();
    const { container } = renderCanvas({
      doc: docWithRef,
      refPreviews: { r2: preview },
      onToggleRef,
    });

    // 被引文档只读子树渲染
    expect(screen.getByTestId("preview-node-b1")).toBeInTheDocument();
    expect(screen.getByTestId("preview-node-b2")).toBeInTheDocument();
    // ref → 预览根 连接线 + 预览内部连线（共 2 条，加主树 1 条 = 3）
    expect(container.querySelectorAll("svg path")).toHaveLength(3);
    // 展开态按钮在 ref 节点右上角（NodeCard 内），文本「收缩」
    expect(screen.getByTestId("node-toggle-r2")).toHaveTextContent("收缩");
    fireEvent.click(screen.getByTestId("node-toggle-r2"));
    expect(onToggleRef).toHaveBeenCalledWith("r2");
  });

  it("点击预览节点回调 onSelectPreview（查看只读属性）", () => {
    const docWithRef: TreeDoc = {
      tree: "A",
      inputs: {},
      outputs: [],
      config: {},
      root: "r1",
      nodes: {
        r1: { id: "r1", type: "Root", name: "根", fields: {}, body: "r2" },
        r2: {
          id: "r2",
          type: "ref",
          name: "去B",
          fields: {},
          target: "B",
          args: [],
          returns: {},
        },
      },
    };
    const preview: TreeDoc = {
      tree: "B",
      inputs: {},
      outputs: [],
      config: {},
      root: "b1",
      nodes: {
        b1: { id: "b1", type: "Root", name: "B根", fields: {}, body: "b2" },
        b2: { id: "b2", type: "Action", name: "动作", fields: { description: "x" } },
      },
    };
    const onSelectPreview = vi.fn();
    renderCanvas({ doc: docWithRef, refPreviews: { r2: preview }, onSelectPreview });
    fireEvent.click(screen.getByTestId("preview-node-b1"));
    expect(onSelectPreview).toHaveBeenCalledWith("r2", "b1");
  });

  it("ref 未展开（无预览）时不渲染子树", () => {
    const docWithRef: TreeDoc = {
      tree: "A",
      inputs: {},
      outputs: [],
      config: {},
      root: "r1",
      nodes: {
        r1: { id: "r1", type: "Root", name: "根", fields: {}, body: "r2" },
        r2: {
          id: "r2",
          type: "ref",
          name: "去B",
          fields: {},
          target: "B",
          args: [],
          returns: {},
        },
      },
    };
    renderCanvas({ doc: docWithRef, refPreviews: {}, onToggleRef: vi.fn() });
    expect(screen.getByTestId("node-toggle-r2")).toHaveTextContent("展开");
    expect(screen.queryByTestId("ref-preview")).not.toBeInTheDocument();
  });

  it("无根节点时渲染空画布占位", () => {
    const empty: TreeDoc = { ...DOC, root: "missing", nodes: {} };
    renderCanvas({ doc: empty });
    expect(screen.getByText("画布为空")).toBeInTheDocument();
  });
});