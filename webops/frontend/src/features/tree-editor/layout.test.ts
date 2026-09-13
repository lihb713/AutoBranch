import { describe, expect, it } from "vitest";

import { layoutDocument, layoutTree, NODE_H, NODE_W } from "./layout";
import type { TreeDoc, TreeNode } from "./treeModel";

function nodes(spec: Record<string, Partial<TreeNode>>): Record<string, TreeNode> {
  const out: Record<string, TreeNode> = {};
  for (const [id, n] of Object.entries(spec)) {
    const node: TreeNode = {
      id,
      type: (n.type ?? "Sequence") as TreeNode["type"],
      name: n.name ?? id,
      fields: n.fields ?? {},
    };
    if (n.body) node.body = n.body;
    if (n.actions) node.actions = n.actions;
    if (n.action) node.action = n.action;
    if (n.branches) node.branches = n.branches;
    out[id] = node;
  }
  return out;
}

describe("layout", () => {
  it("根在上、子在下、兄弟水平", () => {
    const n = nodes({
      n1: { type: "Root", body: "n2" },
      n2: { type: "Sequence", actions: ["n3", "n4"] },
      n3: { type: "Action" },
      n4: { type: "Action" },
    });
    const { boxes } = layoutTree("n1", n);
    const root = boxes.get("n1")!;
    const seq = boxes.get("n2")!;
    const s3 = boxes.get("n3")!;
    const s4 = boxes.get("n4")!;
    expect(root.y).toBeLessThan(seq.y);
    expect(seq.y).toBeLessThan(s3.y);
    expect(s3.y).toBe(s4.y);
    expect(s3.y - seq.y).toBe(NODE_H + 56);
    expect(s3.x).not.toBe(s4.x);
    expect(root.x).toBeCloseTo((s3.x + s4.x + NODE_W) / 2 - NODE_W / 2, 0);
  });

  it("单节点树", () => {
    const n = nodes({ n1: { type: "Root" } });
    const { boxes, width, height } = layoutTree("n1", n);
    expect(boxes.size).toBe(1);
    expect(width).toBe(NODE_W);
    expect(height).toBe(NODE_H);
  });

  it("游离树排布在主树下方", () => {
    const n = nodes({
      n1: { type: "Root", body: "n2" },
      n2: { type: "Action" },
      f1: { type: "Action", name: "游离" },
    });
    const { boxes } = layoutDocument("n1", ["f1"], n);
    expect(boxes.get("f1")!.y).toBeGreaterThan(boxes.get("n2")!.y);
  });

  it("环保护不无限递归", () => {
    const n = nodes({
      n1: { type: "Root", body: "n2" },
      n2: { type: "Sequence", actions: ["n1"] },
    });
    const { boxes } = layoutTree("n1", n);
    expect(boxes.size).toBe(2);
  });

  it("ref 展开预览并入主树布局（向下生长不重叠）", () => {
    const doc = nodes({
      r1: { type: "Root", body: "s1" },
      s1: { type: "Sequence", actions: ["ref1"] },
      ref1: { type: "ref" },
    });
    const preview: TreeDoc = {
      tree: "B",
      inputs: {},
      outputs: [],
      config: {},
      root: "b1",
      nodes: {
        b1: { id: "b1", type: "Root", name: "B根", fields: {}, body: "b2" },
        b2: { id: "b2", type: "Sequence", name: "B主", fields: {}, actions: ["b3"] },
        b3: { id: "b3", type: "Action", name: "动作", fields: { description: "x" } },
      },
    };
    const { boxes } = layoutDocument("r1", [], doc, { ref1: preview });
    // 预览节点以 ref1: 前缀并入主树布局
    expect(boxes.has("ref1:b1")).toBe(true);
    expect(boxes.has("ref1:b3")).toBe(true);
    // 向下生长：ref 在预览根之上，预览根在预览子之上
    expect(boxes.get("ref1")!.y).toBeLessThan(boxes.get("ref1:b1")!.y);
    expect(boxes.get("ref1:b1")!.y).toBeLessThan(boxes.get("ref1:b3")!.y);
    // 不重叠：预览根位于 ref 卡片之下
    expect(boxes.get("ref1:b1")!.y).toBeGreaterThanOrEqual(boxes.get("ref1")!.y + NODE_H);
  });
});