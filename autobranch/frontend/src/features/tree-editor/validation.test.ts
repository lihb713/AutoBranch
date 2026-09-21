import { describe, expect, it } from "vitest";

import { parseDoc, type TreeDoc } from "./treeModel";
import {
  checkAcyclic,
  collectDeclaredVars,
  exprIsVariable,
  validateDoc,
  wouldCreateCycle,
  type ValidateContext,
} from "./validation";

const DOC_YAML = `tree: 订单流程
inputs: {startOrder: str}
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
    description: 点"登录"
  n4:
    type: ref
    name: 处理B
    target: 文档B
    args: [Param.startOrder]
    returns: {NewParam.result: str}
root: n1
`;

function ctx(overrides?: Partial<ValidateContext>): ValidateContext {
  return {
    docNames: ["订单流程", "文档B"],
    refMeta: {
      文档B: { inputs: { startOrder: "str" }, outputs: ["处理结果"] },
    },
    refTargetsOf: () => [],
    ...overrides,
  };
}

describe("validation（统一槽位）", () => {
  it("合法文档无问题", () => {
    const doc = parseDoc(DOC_YAML);
    expect(validateDoc(doc, ctx())).toEqual([]);
  });

  it("单根：多个 Root 报错", () => {
    const doc: TreeDoc = {
      tree: "x",
      inputs: {},
      outputs: [],
      config: {},
      root: "n1",
      nodes: {
        n1: { id: "n1", type: "Root", name: "a", fields: {}, body: "n2" },
        n2: { id: "n2", type: "Root", name: "b", fields: {} },
      },
    };
    const issues = validateDoc(doc, ctx());
    expect(issues.some((i) => i.code === "single_root")).toBe(true);
  });

  it("孤儿槽位引用报错", () => {
    const doc: TreeDoc = {
      tree: "x",
      inputs: {},
      outputs: [],
      config: {},
      root: "n1",
      nodes: {
        n1: { id: "n1", type: "Root", name: "根", fields: {}, body: "n9" },
      },
    };
    const issues = validateDoc(doc, ctx());
    expect(issues.some((i) => i.code === "orphan_slot")).toBe(true);
  });

  it("重复引用报错（纯树）", () => {
    const doc: TreeDoc = {
      tree: "x",
      inputs: {},
      outputs: [],
      config: {},
      root: "n1",
      nodes: {
        n1: { id: "n1", type: "Root", name: "根", fields: {}, body: "n2" },
        n2: { id: "n2", type: "Sequence", name: "s", fields: {}, actions: ["n3", "n3"] },
        n3: { id: "n3", type: "Action", name: "a", fields: { description: "x" } },
      },
    };
    const issues = validateDoc(doc, ctx());
    expect(issues.some((i) => i.code === "duplicate_reference")).toBe(true);
  });

  it("必填槽位与标量字段", () => {
    const yaml = `tree: 缺
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: Step
    name: s
    expect: ok
  n3:
    type: Action
    name: a
    description: x
root: n1
`;
    const doc = parseDoc(yaml);
    const issues = validateDoc(doc, ctx());
    // Step 缺 action 槽位
    expect(issues.some((i) => i.code === "missing_slot")).toBe(true);
  });

  it("Step 缺 expect 报错", () => {
    const doc = parseDoc(DOC_YAML);
    const broken: TreeDoc = { ...doc, nodes: { ...doc.nodes, n3: { ...doc.nodes["n3"], fields: {} } } };
    const issues = validateDoc(broken, ctx());
    expect(issues.some((i) => i.code === "missing_field" && i.field === "expect")).toBe(true);
  });

  it("ref 目标不存在报错", () => {
    const doc = parseDoc(DOC_YAML);
    const issues = validateDoc(doc, ctx({ docNames: ["订单流程"] }));
    expect(issues.some((i) => i.code === "missing_doc")).toBe(true);
  });

  it("ref 参数数量不匹配报错", () => {
    const doc = parseDoc(DOC_YAML);
    const broken: TreeDoc = {
      ...doc,
      nodes: { ...doc.nodes, n4: { ...doc.nodes["n4"], args: [] } },
    };
    const issues = validateDoc(broken, ctx());
    expect(issues.some((i) => i.code === "args_mismatch")).toBe(true);
  });

  it("跨文档环检测", () => {
    expect(
      wouldCreateCycle("文档B", "订单流程", (name) =>
        name === "文档B" ? ["订单流程"] : [],
      ),
    ).toBe(true);
    expect(wouldCreateCycle("文档C", "订单流程", () => [])).toBe(false);
  });

  it("checkAcyclic 检测槽位环", () => {
    const doc: TreeDoc = {
      tree: "x",
      inputs: {},
      outputs: [],
      config: {},
      root: "n1",
      nodes: {
        n1: { id: "n1", type: "Root", name: "根", fields: {}, body: "n2" },
        n2: { id: "n2", type: "Sequence", name: "s", fields: {}, actions: ["n1"] },
      },
    };
    const issues = checkAcyclic(doc);
    expect(issues.some((i) => i.code === "cycle")).toBe(true);
  });

  it("collectDeclaredVars 收集 set 目标与 returns 键", () => {
    const doc = parseDoc(DOC_YAML);
    expect(collectDeclaredVars(doc)).toEqual(new Set(["startOrder", "result"]));
    expect(exprIsVariable(doc, "Param.startOrder")).toBe(true);
    expect(exprIsVariable(doc, "Param.result")).toBe(true);
    expect(exprIsVariable(doc, "Param.missing")).toBe(false);
  });

  it("字面量类型不匹配报错", () => {
    const yaml = `tree: 主流程
inputs: {url: int}
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: ref
    name: B
    target: 文档B
    args: ["abc"]
root: n1
`;
    const doc = parseDoc(yaml);
    const issues = validateDoc(
      doc,
      ctx({
        docNames: ["主流程", "文档B"],
        refMeta: { 文档B: { inputs: { url: "int" }, outputs: [] } },
      }),
    );
    expect(issues.some((i) => i.code === "type_mismatch")).toBe(true);
  });

  it("描述中 Param/NewParam 非 ASCII 变量名报错", () => {
    const yaml = `tree: 主流程
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: Action
    name: 提取
    description: 提取 NewParam.苹果金额:int
root: n1
`;
    const doc = parseDoc(yaml);
    const issues = validateDoc(doc, ctx());
    expect(issues.some((i) => i.code === "syntax.invalid_name")).toBe(true);
  });

  it("returns 裸键（无 NewParam）报 invalid_return_name", () => {
    const yaml = `tree: 主流程
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: FunctionCall
    name: 求和
    function: compute.add
    args: [Param.a, Param.b]
    returns: {total: int}
root: n1
`;
    const doc = parseDoc(yaml);
    const issues = validateDoc(doc, ctx());
    expect(issues.some((i) => i.code === "syntax.invalid_return_name")).toBe(true);
  });

  it("returns 中文 NewParam 键报 invalid_return_name", () => {
    const yaml = `tree: 主流程
nodes:
  n1:
    type: Root
    name: 根
    body: n2
  n2:
    type: FunctionCall
    name: 求和
    function: compute.add
    args: [Param.a, Param.b]
    returns: {NewParam.合计: int}
root: n1
`;
    const doc = parseDoc(yaml);
    const issues = validateDoc(doc, ctx());
    expect(issues.some((i) => i.code === "syntax.invalid_return_name")).toBe(true);
  });
});