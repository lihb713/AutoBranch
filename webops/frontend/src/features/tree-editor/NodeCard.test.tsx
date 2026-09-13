import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NodeCard } from "./NodeCard";
import type { TreeNode } from "./treeModel";

function node(over?: Partial<TreeNode>): TreeNode {
  return { id: "n1", type: "Step", name: "步骤", fields: {}, ...over };
}

function renderCard(props: Partial<Parameters<typeof NodeCard>[0]> = {}) {
  return render(
    <NodeCard
      node={node()}
      selected={false}
      issueFields={new Set<string>()}
      onClick={() => {}}
      onDelete={() => {}}
      {...props}
    />,
  );
}

describe("NodeCard", () => {
  it("显示类型徽标与 name", () => {
    renderCard();
    expect(screen.getByTestId("node-type-n1")).toHaveTextContent("Step");
    expect(screen.getByTestId("node-name-n1")).toHaveTextContent("步骤");
  });

  it("name 为空时回退显示类型名", () => {
    renderCard({ node: node({ name: "   " }) });
    expect(screen.getByTestId("node-name-n1")).toHaveTextContent("Step");
  });

  it("存在 issue 字段时加红框类", () => {
    renderCard({ issueFields: new Set(["*"]) });
    expect(screen.getByTestId("node-card-n1").className).toContain("node-card--issue");
  });

  it("Root 节点删除按钮禁用", () => {
    renderCard({ node: node({ type: "Root" }) });
    expect(screen.getByTestId("node-delete-n1")).toBeDisabled();
    expect(screen.getByTestId("node-delete-subtree-n1")).toBeDisabled();
  });

  it("点击删除调用 onDelete（单节点/子树）", () => {
    const onDelete = vi.fn();
    renderCard({ onDelete });
    fireEvent.click(screen.getByTestId("node-delete-n1"));
    expect(onDelete).toHaveBeenCalledWith("n1", false);
    fireEvent.click(screen.getByTestId("node-delete-subtree-n1"));
    expect(onDelete).toHaveBeenCalledWith("n1", true);
  });

  it("选中态加高亮类", () => {
    renderCard({ selected: true });
    expect(screen.getByTestId("node-card-n1").className).toContain("node-card--selected");
  });
});
