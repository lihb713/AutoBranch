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

  it("选中态加高亮类", () => {
    renderCard({ selected: true });
    expect(screen.getByTestId("node-card-n1").className).toContain("node-card--selected");
  });

  it("点击卡片回调 onClick", () => {
    const onClick = vi.fn();
    renderCard({ onClick });
    fireEvent.click(screen.getByTestId("node-card-n1"));
    expect(onClick).toHaveBeenCalledWith("n1");
  });

  it("ref 节点显示展开按钮（右上角），点击触发 onToggleRef", () => {
    const onToggleRef = vi.fn();
    renderCard({ node: node({ type: "ref" }), onToggleRef, expanded: false });
    const toggle = screen.getByTestId("node-toggle-n1");
    expect(toggle).toHaveTextContent("展开");
    fireEvent.click(toggle);
    expect(onToggleRef).toHaveBeenCalled();
  });

  it("ref 展开态按钮文本为收缩", () => {
    renderCard({ node: node({ type: "ref" }), onToggleRef: () => {}, expanded: true });
    expect(screen.getByTestId("node-toggle-n1")).toHaveTextContent("收缩");
  });

  it("非 ref 节点不显示展开按钮", () => {
    renderCard();
    expect(screen.queryByTestId("node-toggle-n1")).not.toBeInTheDocument();
  });
});