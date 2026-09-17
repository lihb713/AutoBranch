import { describe, expect, it } from "vitest";

import {
  createStepWithAction,
  deleteSubtree,
  detachSlot,
  freeRoots,
  makeNode,
  nextNodeId,
  parseDoc,
  referencedIds,
  removeNode,
  serializeDoc,
  setSlot,
  slotFields,
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
    body: n2
  n2:
    type: Sequence
    name: 主流程
    actions: [n3, n4]
  n3:
    type: Step
    name: 登录
    action: n5
    expect: 出现"工作台"
  n5:
    type: Action
    name: 点登录
    description: 点击"登录"按钮
  n4:
    type: ref
    name: 处理B
    target: 文档B
    args: [起始订单]
    returns: {结果: str}
root: n1
`;

describe("treeModel（统一槽位）", () => {
  it("nextNodeId 跳过已占用", () => {
    const doc = parseDoc(DOC_YAML);
    expect(nextNodeId(doc.nodes)).toBe("n6");
  });

  it("makeNode 按类型初始化槽位/ref 字段", () => {
    const nodes = {};
    expect(makeNode("Sequence", "n9", nodes).actions).toEqual([]);
    expect(makeNode("Branch", "n9", nodes).branches).toEqual([]);
    const ref = makeNode("ref", "n9", nodes);
    expect(ref.target).toBe("");
    expect(ref.args).toEqual([]);
    expect(ref.returns).toEqual({});
  });

  it("parseDoc 解析文档级接口与配置", () => {
    const doc = parseDoc(DOC_YAML);
    expect(doc.tree).toBe("订单流程");
    expect(doc.inputs).toEqual({ 起始订单: "str" });
    expect(doc.outputs).toEqual(["处理结果"]);
    expect(doc.config).toEqual({ timeout: 30 });
    expect(doc.root).toBe("n1");
  });

  it("parseDoc 解析槽位字段与标量字段", () => {
    const doc = parseDoc(DOC_YAML);
    expect(doc.nodes["n1"].body).toBe("n2");
    expect(doc.nodes["n2"].actions).toEqual(["n3", "n4"]);
    expect(doc.nodes["n3"].action).toBe("n5");
    expect(doc.nodes["n3"].fields["expect"]).toBe('出现"工作台"');
    expect(doc.nodes["n5"].fields["description"]).toBe('点击"登录"按钮');
  });

  it("parseDoc 解析 ref 节点", () => {
    const doc = parseDoc(DOC_YAML);
    const ref = doc.nodes["n4"];
    expect(ref.target).toBe("文档B");
    expect(ref.args).toEqual(["起始订单"]);
    expect(ref.returns).toEqual({ 结果: "str" });
  });

  it("slotFields 按类型返回挂载点", () => {
    const doc = parseDoc(DOC_YAML);
    expect(slotFields(doc.nodes["n1"])).toEqual([{ field: "body", label: "主体", childId: "n2" }]);
    expect(slotFields(doc.nodes["n2"]).map((m) => m.childId)).toEqual(["n3", "n4"]);
    expect(slotFields(doc.nodes["n3"])).toEqual([{ field: "action", label: "操作", childId: "n5" }]);
    expect(slotFields(doc.nodes["n5"])).toEqual([]);
  });

  it("referencedIds 与 freeRoots", () => {
    const doc = parseDoc(DOC_YAML);
    expect(referencedIds(doc)).toEqual(new Set(["n2", "n3", "n4", "n5"]));
    expect(freeRoots(doc)).toEqual([]);
  });

  it("游离树根判定", () => {
    const doc: TreeDoc = {
      tree: "x",
      inputs: {},
      outputs: [],
      config: {},
      root: "n1",
      nodes: {
        n1: { id: "n1", type: "Root", name: "根", fields: {}, body: "n2" },
        n2: { id: "n2", type: "Sequence", name: "s", fields: {}, actions: [] },
        n3: { id: "n3", type: "Action", name: "游离", fields: { description: "a" } },
      },
    };
    expect(freeRoots(doc)).toEqual(["n3"]);
  });

  it("serializeDoc 往返无损（含 ref 参数与槽位字段）", () => {
    const doc = parseDoc(DOC_YAML);
    const rebuilt = parseDoc(serializeDoc(doc));
    expect(rebuilt.tree).toBe(doc.tree);
    expect(rebuilt.inputs).toEqual(doc.inputs);
    expect(rebuilt.outputs).toEqual(doc.outputs);
    expect(rebuilt.config).toEqual(doc.config);
    expect(rebuilt.nodes["n1"].body).toBe("n2");
    expect(rebuilt.nodes["n2"].actions).toEqual(["n3", "n4"]);
    expect(rebuilt.nodes["n3"].action).toBe("n5");
    expect(rebuilt.nodes["n4"].target).toBe("文档B");
    expect(rebuilt.nodes["n4"].args).toEqual(["起始订单"]);
    expect(rebuilt.nodes["n4"].returns).toEqual({ 结果: "str" });
  });

  it("Branch 分支行解析与序列化往返", () => {
    const yaml = `tree: 审批
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: Branch
    name: 处理
    action: n3
    branches:
      - when: 出现已批准
        action: n4
      - otherwise: n5
  n3:
    type: Action
    name: 查状态
    description: 查询
  n4:
    type: Action
    name: 导出
    description: 导出
  n5:
    type: Action
    name: 重试
    description: 重试
root: n1
`;
    const doc = parseDoc(yaml);
    const branch = doc.nodes["n2"];
    expect(branch.action).toBe("n3");
    expect(branch.branches).toEqual([
      { when: "出现已批准", action: "n4" },
      { otherwise: "n5" },
    ]);
    const rebuilt = parseDoc(serializeDoc(doc));
    expect(rebuilt.nodes["n2"].branches).toEqual(branch.branches);
    // 挂载点：action + 两个分支
    expect(slotFields(branch).map((m) => m.childId)).toEqual(["n3", "n4", "n5"]);
  });

  it("detachSlot 删除槽位 = 解引用回游离区", () => {
    const doc = parseDoc(DOC_YAML);
    const next = detachSlot(doc, "n2", 0); // 移除 actions[0]=n3
    expect(next.nodes["n2"].actions).toEqual(["n4"]);
    expect(freeRoots(next)).toContain("n3");
  });

  it("detachSlot 解引用单槽字段（Step.action）", () => {
    const doc = parseDoc(DOC_YAML);
    const next = detachSlot(doc, "n3", 0);
    expect(next.nodes["n3"].action).toBeUndefined();
    expect(freeRoots(next)).toContain("n5");
  });

  it("setSlot 改槽位：旧节点回游离区、新节点入", () => {
    const doc = parseDoc(DOC_YAML);
    const next = setSlot(doc, "n2", 1, "n3"); // actions[1] n4 → n3
    expect(next.nodes["n2"].actions).toEqual(["n3", "n3"]);
    expect(freeRoots(next)).toContain("n4");
  });

  it("removeNode 删除单节点：子节点各自成游离树、父槽位清除", () => {
    const doc = parseDoc(DOC_YAML);
    const next = removeNode(doc, "n2")!;
    expect(next.nodes["n2"]).toBeUndefined();
    expect(next.nodes["n1"].body).toBeUndefined();
    expect(freeRoots(next).sort()).toEqual(["n3", "n4"]);
  });

  it("removeNode 拒绝删除根节点", () => {
    const doc = parseDoc(DOC_YAML);
    expect(removeNode(doc, "n1")).toBeNull();
  });

  it("deleteSubtree 删除节点与全部后代", () => {
    const doc = parseDoc(DOC_YAML);
    const next = deleteSubtree(doc, "n3")!; // n3 → n5 连带删除
    expect(next.nodes["n3"]).toBeUndefined();
    expect(next.nodes["n5"]).toBeUndefined();
    expect(next.nodes["n2"].actions).toEqual(["n4"]);
  });

  it("deleteSubtree 拒绝删除根", () => {
    const doc = parseDoc(DOC_YAML);
    expect(deleteSubtree(doc, "n1")).toBeNull();
  });

  it("createStepWithAction 创建 Step 并自动附 Action", () => {
    const doc = parseDoc(DOC_YAML);
    const { doc: next, stepId } = createStepWithAction(doc);
    expect(next.nodes[stepId].type).toBe("Step");
    const actionId = next.nodes[stepId].action;
    expect(actionId).toBeTruthy();
    expect(next.nodes[actionId!].type).toBe("Action");
  });
});