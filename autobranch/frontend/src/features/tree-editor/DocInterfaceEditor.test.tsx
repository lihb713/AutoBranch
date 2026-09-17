import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DocInterfaceEditor } from "./DocInterfaceEditor";
import type { TreeDoc } from "./treeModel";

const DOC: TreeDoc = {
  tree: "订单流程",
  inputs: { 起始订单: "str" },
  outputs: ["处理结果"],
  config: {},
  root: "n1",
  nodes: {
    n1: { id: "n1", type: "Root", name: "根", fields: {}, body: "n2" },
    n2: { id: "n2", type: "Action", name: "操作", fields: { description: "x" } },
  },
};

function renderEditor(props: Partial<Parameters<typeof DocInterfaceEditor>[0]> = {}) {
  return render(
    <DocInterfaceEditor doc={DOC} onUpdate={() => {}} {...props} />,
  );
}

describe("DocInterfaceEditor", () => {
  it("渲染树名与 inputs/outputs", () => {
    renderEditor();
    expect(screen.getByText(/订单流程/)).toBeInTheDocument();
    expect(screen.getByTestId("doc-input-name-起始订单")).toHaveValue("起始订单");
    expect(screen.getByTestId("doc-output-name-0")).toHaveValue("处理结果");
  });

  it("添加入参：生成新键并回调 onUpdate", () => {
    const onUpdate = vi.fn();
    renderEditor({ onUpdate });
    fireEvent.click(screen.getByTestId("doc-input-add"));
    const next = onUpdate.mock.calls[0][0] as TreeDoc;
    expect(Object.keys(next.inputs)).toContain("入参2");
    expect(next.inputs["入参2"]).toBe("str");
  });

  it("修改入参名与类型", () => {
    const onUpdate = vi.fn();
    renderEditor({ onUpdate });
    fireEvent.change(screen.getByTestId("doc-input-type-起始订单"), {
      target: { value: "int" },
    });
    const next = onUpdate.mock.calls[0][0] as TreeDoc;
    expect(next.inputs["起始订单"]).toBe("int");
  });

  it("删除入参", () => {
    const onUpdate = vi.fn();
    renderEditor({ onUpdate });
    fireEvent.click(screen.getByTestId("doc-input-remove-起始订单"));
    const next = onUpdate.mock.calls[0][0] as TreeDoc;
    expect(next.inputs).toEqual({});
  });

  it("添加/删除出参", () => {
    const onUpdate = vi.fn();
    renderEditor({ onUpdate });
    fireEvent.click(screen.getByTestId("doc-output-add"));
    let next = onUpdate.mock.calls[0][0] as TreeDoc;
    expect(next.outputs).toContain("出参2");
    fireEvent.click(screen.getByTestId("doc-output-remove-0"));
    next = onUpdate.mock.calls[1][0] as TreeDoc;
    expect(next.outputs).not.toContain("处理结果");
  });

  it("readonly 模式：禁用编辑、隐藏增删按钮", () => {
    renderEditor({ readonly: true });
    expect(screen.getByTestId("doc-input-name-起始订单")).toBeDisabled();
    expect(screen.queryByTestId("doc-input-add")).not.toBeInTheDocument();
    expect(screen.queryByTestId("doc-output-add")).not.toBeInTheDocument();
  });
});