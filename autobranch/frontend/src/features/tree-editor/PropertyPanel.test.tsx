import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PropertyPanel } from "./PropertyPanel";
import type { TreeDoc, TreeNode } from "./treeModel";
import type { RefMeta } from "./validation";

const functionMocks = vi.hoisted(() => ({
  listFunctions: vi.fn(),
}));

vi.mock("../../api/plugins", () => ({
  pluginsApi: { listFunctions: functionMocks.listFunctions },
}));

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
      returns: { "NewParam.result": "str" },
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
  beforeEach(() => {
    functionMocks.listFunctions.mockReset();
    functionMocks.listFunctions.mockResolvedValue([]);
  });

  const openOptions = (testid: string): string[] => {
    fireEvent.focus(screen.getByTestId(testid));
    return screen.getAllByRole("option").map((o) => o.textContent?.trim() ?? "");
  };

  const pickOption = (testid: string, label: string) => {
    fireEvent.focus(screen.getByTestId(testid));
    const opt = screen.getAllByRole("option").find((o) => o.textContent?.trim() === label);
    expect(opt).toBeDefined();
    fireEvent.mouseDown(opt!);
    return opt;
  };

  it("槽位下拉只含游离树根（不含已挂载/树内非根/根节点）", () => {
    renderPanel(DOC, DOC.nodes.n2);
    const labels = openOptions("slot-n2-0");
    expect(labels).toEqual(["（空）", "登录", "游离一", "游离二"]);
    expect(labels).not.toContain("点登录");
    expect(labels).not.toContain("根");
  });

  it("选择游离根即挂载（onUpdate 回传新 doc）", () => {
    const onUpdate = vi.fn();
    renderPanel(DOC, DOC.nodes.n2, { onUpdate });
    pickOption("slot-n2-0", "游离一");
    expect(onUpdate).toHaveBeenCalledTimes(1);
    const next = onUpdate.mock.calls[0][0] as TreeDoc;
    expect(next.nodes.n2.actions).toEqual(["f1"]);
  });

  it("槽位下拉支持输入过滤", () => {
    renderPanel(DOC, DOC.nodes.n2);
    const input = screen.getByTestId("slot-n2-0");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "游离" } });
    const labels = screen.getAllByRole("option").map((o) => o.textContent?.trim() ?? "");
    expect(labels).toEqual(["游离一", "游离二"]);
  });

  it("描述字段渲染 Param/NewParam 高亮", () => {
    const action: TreeNode = {
      id: "a1",
      type: "Action",
      name: "操作",
      fields: { description: "访问 Param.base_url 并保存为 NewParam.siteUrl:str" },
    };
    const doc: TreeDoc = {
      tree: "主流程",
      inputs: {},
      outputs: [],
      config: {},
      root: "r1",
      nodes: {
        r1: { id: "r1", type: "Root", name: "根", fields: {}, body: "a1" },
        a1: action,
      },
    };
    const { container } = renderPanel(doc, action, {});
    expect(container.querySelectorAll(".hl-param")).toHaveLength(1);
    expect(container.querySelectorAll(".hl-newparam")).toHaveLength(1);
    expect(container.querySelector(".hl-param")).toHaveTextContent("Param.base_url");
    expect(container.querySelector(".hl-newparam")).toHaveTextContent("NewParam.siteUrl:str");
  });

  it("Sequence 增加槽位追加空占位", () => {
    const onUpdate = vi.fn();
    renderPanel(DOC, DOC.nodes.n2, { onUpdate });
    fireEvent.click(screen.getByTestId("add-slot-n2"));
    const next = onUpdate.mock.calls[0][0] as TreeDoc;
    expect(next.nodes.n2.actions).toEqual(["n3", ""]);
  });

  it("空 Sequence（无槽位）仍显示「增加槽位」按钮", () => {
    const seqNode: TreeNode = {
      id: "s1",
      type: "Sequence",
      name: "顺序",
      fields: {},
      actions: [],
    };
    const doc: TreeDoc = {
      tree: "主流程",
      inputs: {},
      outputs: [],
      config: {},
      root: "r1",
      nodes: {
        r1: { id: "r1", type: "Root", name: "根", fields: {}, body: "s1" },
        s1: seqNode,
      },
    };
    const onUpdate = vi.fn();
    renderPanel(doc, seqNode, { onUpdate });
    fireEvent.click(screen.getByTestId("add-slot-s1"));
    const next = onUpdate.mock.calls[0][0] as TreeDoc;
    expect(next.nodes.s1.actions).toEqual([""]);
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
    const labels = openOptions("ref-target-r2");
    expect(labels).toContain("文档B");
    expect(labels).toContain("文档C");
    expect(labels).not.toContain("主流程");

    expect(screen.getByTestId("ref-arg-r2-0")).toHaveValue("url");
    expect(screen.getByTestId("ref-return-name-r2-0")).toHaveValue("NewParam.result");
    expect(screen.getByTestId("ref-return-type-r2-0")).toHaveValue("str");
  });

  it("ref：选择目标文档触发 onLoadRefMeta", () => {
    const onUpdate = vi.fn();
    const onLoadRefMeta = vi.fn();
    renderPanel(REF_DOC, REF_DOC.nodes.r2, { onUpdate, onLoadRefMeta });
    pickOption("ref-target-r2", "文档C");
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
    pickOption("ref-target-r2", "文档C");
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
      target: { value: "NewParam.result2" },
    });
    const next = onUpdate.mock.calls[0][0] as TreeDoc;
    expect(next.nodes.r2.returns).toEqual({ "NewParam.result2": "str" });
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

  it("readonly 模式：字段/槽位禁用、无删除与增删按钮", () => {
    renderPanel(DOC, DOC.nodes.n3, { readonly: true });
    expect(screen.getByTestId("field-n3-expect")).toBeDisabled();
    expect(screen.getByTestId("slot-n3-0")).toBeDisabled();
    expect(screen.queryByTestId("delete-node")).not.toBeInTheDocument();
    expect(screen.queryByTestId("delete-subtree")).not.toBeInTheDocument();
  });

  it("readonly 模式：ref 节点目标下拉与参数禁用", () => {
    const refMeta: Record<string, RefMeta> = {
      文档B: { inputs: { url: "str" }, outputs: ["处理结果"] },
    };
    renderPanel(REF_DOC, REF_DOC.nodes.r2, { refMeta, readonly: true });
    expect(screen.getByTestId("ref-target-r2")).toBeDisabled();
    expect(screen.getByTestId("ref-arg-r2-0")).toBeDisabled();
  });

  it("FunctionCall：函数名可搜索下拉罗列全名并选择", async () => {
    functionMocks.listFunctions.mockResolvedValue([
      {
        full_name: "compute.add",
        plugin: "compute",
        name: "add",
        description: "加法",
        returns: [],
        parameters: {},
      },
      {
        full_name: "compute.multiply",
        plugin: "compute",
        name: "multiply",
        description: "乘法",
        returns: [],
        parameters: {},
      },
    ]);
    const fc: TreeNode = {
      id: "fc1",
      type: "FunctionCall",
      name: "求和",
      fields: {},
      function: "",
      args: [],
      returns: {},
    };
    const doc: TreeDoc = {
      tree: "主流程",
      inputs: {},
      outputs: [],
      config: {},
      root: "r1",
      nodes: {
        r1: { id: "r1", type: "Root", name: "根", fields: {}, body: "fc1" },
        fc1: fc,
      },
    };
    const onUpdate = vi.fn();
    renderPanel(doc, fc, { onUpdate });
    const input = screen.getByLabelText("函数名") as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "add" } });
    await waitFor(() =>
      expect(screen.getByRole("option")).toHaveTextContent("compute.add"),
    );
    fireEvent.mouseDown(screen.getByRole("option"));
    const next = onUpdate.mock.calls[0][0] as TreeDoc;
    expect(next.nodes.fc1.function).toBe("compute.add");
  });

  it("FunctionCall：按函数签名自动罗列入参/返回值，无需手动添加", async () => {
    functionMocks.listFunctions.mockResolvedValue([
      {
        full_name: "compute.add",
        plugin: "compute",
        name: "add",
        description: "加法",
        returns: ["result"],
        parameters: {
          type: "object",
          properties: {
            a: { type: "integer", description: "被加数" },
            b: { type: "number", description: "加数" },
          },
          required: ["a", "b"],
        },
      },
    ]);
    const fc: TreeNode = {
      id: "fc2",
      type: "FunctionCall",
      name: "求和",
      fields: {},
      function: "",
      args: [],
      returns: {},
    };
    const doc: TreeDoc = {
      tree: "主流程",
      inputs: {},
      outputs: [],
      config: {},
      root: "r1",
      nodes: {
        r1: { id: "r1", type: "Root", name: "根", fields: {}, body: "fc2" },
        fc2: fc,
      },
    };
    const onUpdate = vi.fn();
    const StatefulPanel = () => {
      const [cur, setCur] = useState(doc);
      return (
        <PropertyPanel
          doc={cur}
          node={cur.nodes.fc2}
          docNames={["主流程", "文档B", "文档C"]}
          refMeta={{}}
          refTargetsOf={() => []}
          onUpdate={(next) => {
            setCur(next);
            onUpdate(next);
          }}
          onLoadRefMeta={() => {}}
          onDeleteNode={() => {}}
        />
      );
    };
    render(<StatefulPanel />);
    expect(screen.getByText("选择函数后自动列出参数")).toBeInTheDocument();

    const input = screen.getByLabelText("函数名") as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "compute.add" } });
    await waitFor(() => expect(screen.getByRole("option")).toHaveTextContent("compute.add"));
    fireEvent.mouseDown(screen.getByRole("option"));

    expect(screen.getByText("入参 a（int）")).toBeInTheDocument();
    expect(screen.getByText("入参 b（float）")).toBeInTheDocument();
    expect(screen.getByText("返回值 result")).toBeInTheDocument();
    expect(screen.getAllByLabelText("接收参数名")).toHaveLength(1);
    expect(screen.queryByText("添加实参")).not.toBeInTheDocument();
    expect(screen.queryByText("添加返回值")).not.toBeInTheDocument();

    const argInputs = screen.getAllByLabelText("入参 a（int）") as HTMLInputElement[];
    fireEvent.change(argInputs[0], { target: { value: "x" } });
    const next = onUpdate.mock.calls[onUpdate.mock.calls.length - 1][0] as TreeDoc;
    expect(next.nodes.fc2.args).toEqual(["x"]);
  });
});
