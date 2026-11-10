import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DocInterfaceEditor } from "./DocInterfaceEditor";
import type { TreeDoc } from "./treeModel";

const DOC: TreeDoc = {
  tree: "订单流程",
  inputs: { startOrder: "str" },
  outputs: { result: "str" },
  config: {},
  root: "n1",
  nodes: {
    n1: { id: "n1", type: "Root", name: "根", fields: {}, body: "n2" },
    n2: { id: "n2", type: "Action", name: "操作", fields: { description: "x" } },
  },
};

function renderEditor(props: Partial<Parameters<typeof DocInterfaceEditor>[0]> = {}) {
  return render(<DocInterfaceEditor doc={DOC} onPatch={() => {}} {...props} />);
}

describe("DocInterfaceEditor", () => {
  it("渲染树名与 inputs/outputs", () => {
    renderEditor();
    expect(screen.getByText(/订单流程/)).toBeInTheDocument();
    expect(screen.getByTestId("doc-input-name-startOrder")).toHaveValue("startOrder");
    expect(screen.getByTestId("doc-output-name-result")).toHaveValue("result");
    expect(screen.getByTestId("doc-output-type-result")).toHaveValue("str");
  });

  it("添加入参：生成 ASCII 默认名并回调 onPatch", () => {
    const onPatch = vi.fn();
    renderEditor({ onPatch });
    fireEvent.click(screen.getByTestId("doc-input-add"));
    const patch = onPatch.mock.calls[0][0] as Partial<TreeDoc>;
    expect(Object.keys(patch.inputs ?? {})).toContain("input1");
    expect(patch.inputs?.input1).toBe("str");
  });

  it("修改入参类型", () => {
    const onPatch = vi.fn();
    renderEditor({ onPatch });
    fireEvent.change(screen.getByTestId("doc-input-type-startOrder"), {
      target: { value: "int" },
    });
    const patch = onPatch.mock.calls[0][0] as Partial<TreeDoc>;
    expect(patch.inputs?.startOrder).toBe("int");
  });

  it("删除入参", () => {
    const onPatch = vi.fn();
    renderEditor({ onPatch });
    fireEvent.click(screen.getByTestId("doc-input-remove-startOrder"));
    const patch = onPatch.mock.calls[0][0] as Partial<TreeDoc>;
    expect(patch.inputs).toEqual({});
  });

  it("添加/删除出参", () => {
    const onPatch = vi.fn();
    renderEditor({ onPatch });
    fireEvent.click(screen.getByTestId("doc-output-add"));
    let patch = onPatch.mock.calls[0][0] as Partial<TreeDoc>;
    expect(Object.keys(patch.outputs ?? {})).toContain("output1");
    fireEvent.click(screen.getByTestId("doc-output-remove-result"));
    patch = onPatch.mock.calls[1][0] as Partial<TreeDoc>;
    expect(patch.outputs?.result).toBeUndefined();
  });
});
