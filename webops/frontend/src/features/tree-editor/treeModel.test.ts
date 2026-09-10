import { describe, expect, it } from "vitest";

import {
  freeRoots,
  makeNode,
  nextNodeId,
  parseDoc,
  referencedIds,
  serializeDoc,
  type TreeDoc,
} from "./treeModel";

const DOC_YAML = `tree: 订单流程
inputs: {起始订单: str}
outputs: [处理结果]
timeout: 30
nodes:
  n1:
    type: Root
    name: 根
    slots: {1: n2}
  n2:
    type: Sequence
    name: 主流程
    slots: {1: n3, 2: n4}
  n3:
    type: Step
    name: 登录
    action: 点"登录"
    expect: 出现"工作台"
  n4:
    type: ref
    name: 处理B
    target: 文档B
    args: [起始订单]
    returns: {结果: str}
root: n1
`;

describe("treeModel", () => {
  it("nextNodeId 跳过已占用", () => {
    const doc = parseDoc(DOC_YAML);
    expect(nextNodeId(doc.nodes)).toBe("n5");
  });

  it("makeNode 生成默认名与空槽位", () => {
    const n = makeNode("Sequence", "n9");
    expect(n.name).toBe("Sequence");
    expect(n.slots).toEqual([]);
  });

  it("makeNode ref 带 target/args/returns", () => {
    const n = makeNode("ref", "n9");
    expect(n.target).toBe("");
    expect(n.args).toEqual([]);
    expect(n.returns).toEqual({});
  });

  it("parseDoc 解析文档级接口与配置", () => {
    const doc = parseDoc(DOC_YAML);
    expect(doc.tree).toBe("订单流程");
    expect(doc.inputs).toEqual({ 起始订单: "str" });
    expect(doc.outputs).toEqual(["处理结果"]);
    expect(doc.config).toEqual({ timeout: 30 });
    expect(doc.root).toBe("n1");
  });

  it("parseDoc 解析节点池与槽位", () => {
    const doc = parseDoc(DOC_YAML);
    expect(Object.keys(doc.nodes).sort()).toEqual(["n1", "n2", "n3", "n4"]);
    expect(doc.nodes["n2"].slots).toEqual(["n3", "n4"]);
    expect(doc.nodes["n3"].fields["action"]).toBe('点"登录"');
  });

  it("parseDoc 解析 ref 节点", () => {
    const doc = parseDoc(DOC_YAML);
    const ref = doc.nodes["n4"];
    expect(ref.type).toBe("ref");
    expect(ref.target).toBe("文档B");
    expect(ref.args).toEqual(["起始订单"]);
    expect(ref.returns).toEqual({ 结果: "str" });
  });

  it("referencedIds 与 freeRoots", () => {
    const doc = parseDoc(DOC_YAML);
    expect(referencedIds(doc)).toEqual(new Set(["n2", "n3", "n4"]));
    expect(freeRoots(doc)).toEqual([]); // n1 是 root，其余都被引用
  });

  it("游离树根判定", () => {
    const doc: TreeDoc = {
      tree: "x",
      inputs: {},
      outputs: [],
      config: {},
      root: "n1",
      nodes: {
        n1: { id: "n1", type: "Root", name: "根", fields: {}, slots: ["n2"] },
        n2: { id: "n2", type: "Sequence", name: "s", fields: {}, slots: [] },
        n3: { id: "n3", type: "Step", name: "游离", fields: {}, slots: [] },
      },
    };
    expect(freeRoots(doc)).toEqual(["n3"]);
  });

  it("serializeDoc 往返无损（含 ref 参数）", () => {
    const doc = parseDoc(DOC_YAML);
    const rebuilt = parseDoc(serializeDoc(doc));
    expect(rebuilt.tree).toBe(doc.tree);
    expect(rebuilt.inputs).toEqual(doc.inputs);
    expect(rebuilt.outputs).toEqual(doc.outputs);
    expect(rebuilt.config).toEqual(doc.config);
    expect(rebuilt.root).toBe(doc.root);
    expect(rebuilt.nodes["n4"].target).toBe("文档B");
    expect(rebuilt.nodes["n4"].args).toEqual(["起始订单"]);
    expect(rebuilt.nodes["n4"].returns).toEqual({ 结果: "str" });
    expect(rebuilt.nodes["n2"].slots).toEqual(["n3", "n4"]);
  });
});