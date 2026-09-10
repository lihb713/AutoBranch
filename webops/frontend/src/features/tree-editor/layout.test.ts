import { describe, expect, it } from "vitest";

import { layoutDocument, layoutTree, NODE_H, NODE_W } from "./layout";
import type { TreeNode } from "./treeModel";

function nodes(spec: Record<string, Partial<TreeNode>>): Record<string, TreeNode> {
  const out: Record<string, TreeNode> = {};
  for (const [id, n] of Object.entries(spec)) {
    out[id] = {
      id,
      type: (n.type ?? "Sequence") as TreeNode["type"],
      name: n.name ?? id,
      fields: n.fields ?? {},
      slots: n.slots ?? [],
    };
  }
  return out;
}

describe("layout", () => {
  it("根在上、子在下、兄弟水平", () => {
    const n = nodes({
      n1: { type: "Root", slots: ["n2"] },
      n2: { type: "Sequence", slots: ["n3", "n4"] },
      n3: { type: "Step" },
      n4: { type: "Step" },
    });
    const { boxes } = layoutTree("n1", n);
    const root = boxes.get("n1")!;
    const seq = boxes.get("n2")!;
    const s3 = boxes.get("n3")!;
    const s4 = boxes.get("n4")!;
    // 向下生长：y 递增
    expect(root.y).toBeLessThan(seq.y);
    expect(seq.y).toBeLessThan(s3.y);
    // 兄弟水平同层：n3/n4 同一 y
    expect(s3.y).toBe(s4.y);
    expect(s3.y - seq.y).toBe(NODE_H + 56);
    // 兄弟水平分布：x 不同
    expect(s3.x).not.toBe(s4.x);
    // 根居中于子树之上
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
      n1: { type: "Root", slots: ["n2"] },
      n2: { type: "Step" },
      f1: { type: "Step", name: "游离" },
    });
    const { boxes } = layoutDocument("n1", ["f1"], n);
    expect(boxes.get("f1")!.y).toBeGreaterThan(boxes.get("n2")!.y);
  });

  it("环保护不无限递归", () => {
    const n = nodes({
      n1: { type: "Root", slots: ["n2"] },
      n2: { type: "Sequence", slots: ["n1"] },
    });
    const { boxes } = layoutTree("n1", n);
    expect(boxes.size).toBe(2);
  });
});