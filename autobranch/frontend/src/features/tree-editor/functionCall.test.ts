import { describe, expect, test } from "vitest";
import { makeNode, parseDoc, serializeDoc } from "./treeModel";

const YAML = `tree: t
nodes:
  n1:
    type: Root
    body: n2
  n2:
    type: FunctionCall
    function: compute.multiply
    args: ["2", "3"]
    returns:
      结果: int
root: n1
`;

describe("FunctionCall 节点", () => {
  test("解析 FunctionCall 字段", () => {
    const doc = parseDoc(YAML);
    const fc = doc.nodes["n2"];
    expect(fc.type).toBe("FunctionCall");
    expect(fc.function).toBe("compute.multiply");
    expect(fc.args).toEqual(["2", "3"]);
    expect(fc.returns).toEqual({ 结果: "int" });
  });

  test("序列化保留 FunctionCall 字段", () => {
    const text = serializeDoc(parseDoc(YAML));
    expect(text).toContain("type: FunctionCall");
    expect(text).toContain("function: compute.multiply");
    expect(text).toContain("结果: int");
  });

  test("makeNode 初始化 FunctionCall 字段", () => {
    const node = makeNode("FunctionCall", "n9", {});
    expect(node.function).toBe("");
    expect(node.args).toEqual([]);
    expect(node.returns).toEqual({});
    expect(node.type).toBe("FunctionCall");
  });
});