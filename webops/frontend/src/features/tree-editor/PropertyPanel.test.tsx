import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PropertyPanel } from "./PropertyPanel";
import type { TreeDoc, TreeNode } from "./treeModel";
import type { RefMeta } from "./validation";

const DOC: TreeDoc = {
  tree: "主流程",
  inputs: {},
  outputs: [],
  config: {},
  root: "n1",
  nodes: {
    n1: { id: "n1", type: "Root", name: "根", fields: {}, body: "n2" },
    n2: { id: "n2", type: "Sequence", name: "主流程", fields: {}, actions: ["n3"] },
    n3: { id: "n3", type: "Step", name: "登录", fields: { expect: "ok" }, action: "n4" },
    n4: { id: "n4", type: "Action", name: "点登录", fields: { description: "点" } },
    f1: { id: "f1", type: "Action", name: "游离一", fields: { description: "a" } },
    f2: { id: "f2", type: "Sequence", name: "游离二", fields: {}, actions: [] },
  },
};

const REF_DOC: TreeDoc = {
  tree: "主流程",
  inputs: {},
  outputs: [],
  config: {},
  root: "r1",
  nodes: {
    r1: { id: "r1", type: "Root", name: "根", fields: {}, body: "r2" },
    r2: {
      id: "r2",
      type: "ref",
      name: "处理B",
      fields: {},
      target: "文档B",
      args: ["url"],
      returns: { 结果: "str" },
    },
  },
};

function renderPanel(
  doc: TreeDoc,
  node: TreeNode | null,
  props: Partial<Parameters<typeof PropertyPanel>[0]> = {},
) {
  return render(
    <PropertyPanel
      doc={doc}
      node={node}
      docNames={["主流程", "文档B", "文档C"]}
      refMeta={{}}
      refTargetsOf={() => []}
      onUpdate={() => {}}
      onLoadRefMeta={() => {}}
      onDeleteNode={() => {}}
      {...props}
    />,
  );
}

describe("PropertyPanel", () => {
  it("槽位下拉只含游离树根（不含已挂载/树内非根/根节点）", () => {
    renderPanel(DOC, DOC.nodes.n2);
    const select = screen.getByTestId("slot-n2-0") as HTMLSelectElement;
    const values = within(select)
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value);
    expect(values).toEqual(["", "n3", "f1", "f2"]);
    expect(values).not.toContain("n4");
    expect(values).not.toContain("n1");
  });

  it("选择游离根即挂载（onUpdate 回传新 doc）", () => {
    const onUpdate = vi.fn();
    renderPanel(DOC, DOC.nodes.n2, { onUpdate });
    fireEvent.change(screen.getByTestId("slot-n2-0"), { target: { value: "f1" } });
    expect(onUpdate).toHaveBeenCalledTimes(1);
    const next = onUpdate.mock.calls[0][0] as TreeDoc;
    expect(next.nodes.n2.actions).toEqual(["f1"]);
  });

  it("Sequence 增加槽位追加空占位", () => {
    const onUpdate = vi.fn();
    renderPanel(DOC, DOC.nodes.n2, { onUpdate });
    fireEvent.click(screen.getByTestId("add-slot-n2"));
    const next = onUpdate.mock.calls[0][0] as TreeDoc;
    expect(next.nodes.n2.actions).toEqual(["n3", ""]);
  });

  it("Step 展示 expect 标量字段", () => {
    renderPanel(DOC, DOC.nodes.n3);
    expect(screen.getByTestId("field-n3-expect")).toHaveValue("ok");
  });

  it("Root 的删除按钮禁用", () => {
    renderPanel(DOC, DOC.nodes.n1);
    expect(screen.getByTestId("delete-node")).toBeDisabled();
    expect(screen.getByTestId("delete-subtree")).toBeDisabled();
  });

  it("ref：目标下拉排除本文档并加载参数表单", () => {
    const refMeta: Record<string, RefMeta> = {
      文档B: { inputs: { url: "str" }, outputs: ["处理结果"] },
    };
    renderPanel(REF_DOC, REF_DOC.nodes.r2, { refMeta });
    const select = screen.getByTestId("ref-target-r2") as HTMLSelectElement;
    const values = within(select)
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value);
    expect(values).toContain("文档B");
    expect(values).toContain("文档C");
    expect(values).not.toContain("主流程");

    expect(screen.getByTestId("ref-arg-r2-0")).toHaveValue("url");
    expect(screen.getByTestId("ref-return-name-r2-0")).toHaveValue("结果");
    expect(screen.getByTestId("ref-return-type-r2-0")).toHaveValue("str");
  });

  it("ref：选择目标文档触发 onLoadRefMeta", () => {
    const onUpdate = vi.fn();
    const onLoadRefMeta = vi.fn();
    renderPanel(REF_DOC, REF_DOC.nodes.r2, { onUpdate, onLoadRefMeta });
    fireEvent.change(screen.getByTestId("ref-target-r2"), { target: { value: "文档C" } });
    expect(onLoadRefMeta).toHaveBeenCalledWith("文档C");
    const next = onUpdate.mock.calls[0][0] as TreeDoc;
    expect(next.nodes.r2.target).toBe("文档C");
  });

  it("ref：跨文档环即时拦截且不更新", () => {
    const onUpdate = vi.fn();
    const onLoadRefMeta = vi.fn();
    renderPanel(REF_DOC, REF_DOC.nodes.r2, {
      onUpdate,
      onLoadRefMeta,
      refTargetsOf: (name) => (name === "文档C" ? ["主流程"] : []),
    });
    fireEvent.change(screen.getByTestId("ref-target-r2"), { target: { value: "文档C" } });
    expect(screen.getByTestId("ref-cycle-error")).toHaveTextContent("跨文档循环");
    expect(onUpdate).not.toHaveBeenCalled();
    expect(onLoadRefMeta).not.toHaveBeenCalled();
  });

  it("ref：编辑出参接收名与类型", () => {
    const onUpdate = vi.fn();
    renderPanel(REF_DOC, REF_DOC.nodes.r2, {
      onUpdate,
      refMeta: { 文档B: { inputs: { url: "str" }, outputs: ["处理结果"] } },
    });
    fireEvent.change(screen.getByTestId("ref-return-name-r2-0"), {
      target: { value: "结果2" },
    });
    const next = onUpdate.mock.calls[0][0] as TreeDoc;
    expect(next.nodes.r2.returns).toEqual({ 结果2: "str" });
  });

  it("Branch 分支增删与 otherwise 切换", () => {
    const branch: TreeNode = {
      id: "b1",
      type: "Branch",
      name: "分流",
      fields: {},
      action: "",
      branches: [{ when: "出现成功" }],
    };
    const doc: TreeDoc = {
      tree: "主流程",
      inputs: {},
      outputs: [],
      config: {},
      root: "r1",
      nodes: {
        r1: { id: "r1", type: "Root", name: "根", fields: {}, body: "b1" },
        b1: branch,
        f1: { id: "f1", type: "Action", name: "游离", fields: { description: "a" } },
      },
    };
    const onUpdate = vi.fn();
    renderPanel(doc, branch, { onUpdate });
    fireEvent.click(screen.getByTestId("add-branch-b1"));
    expect((onUpdate.mock.calls[0][0] as TreeDoc).nodes.b1.branches).toHaveLength(2);
    onUpdate.mockClear();

    fireEvent.click(screen.getByTestId("branch-remove-b1-0"));
    expect((onUpdate.mock.calls[0][0] as TreeDoc).nodes.b1.branches).toHaveLength(0);
  });
});
