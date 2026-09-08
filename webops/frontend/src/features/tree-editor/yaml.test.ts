import { describe, expect, it } from "vitest";
import { load } from "js-yaml";
import type { EditorNode } from "../../types/node";
import { makeNode, nodeToYamlValue, parseTree, serializeTree } from "./model";

function stripIds(node: EditorNode): unknown {
  return {
    type: node.type,
    fields: node.fields,
    children: node.children.map(stripIds),
  };
}

function fullTree(): EditorNode {
  return makeNode("Sequence", [], [
    makeNode("Step", [
      { key: "action", value: "点\"登录\"" },
      { key: "expect", value: "出现\"工作台\"" },
    ]),
    makeNode("Branch", [{ key: "action", value: "点\"提交\"" }], [
      makeNode("branch", [
        { key: "when", value: "出现\"成功\"" },
        { key: "then", value: "完成流程" },
      ]),
      makeNode("branch", [{ key: "otherwise", value: "终止流程" }]),
    ]),
    makeNode("LoopUntil", [
      { key: "action", value: "点\"批准\"" },
      { key: "until", value: "无\"批准\"按钮" },
      { key: "max", value: "50" },
    ]),
    makeNode("IfThenElse", [
      { key: "if", value: "存在\"下载成功\"提示" },
      { key: "then", value: "完成流程" },
      { key: "else", value: "重试下载" },
    ]),
    makeNode("Retry", [{ key: "max", value: "3" }], [
      makeNode("Step", [
        { key: "action", value: "点\"下载\"" },
        { key: "expect", value: "出现\"下载成功\"" },
      ]),
    ]),
    makeNode("ref", [{ key: "ref", value: "this/登录" }]),
  ]);
}

describe("yaml 生成与解析（复合节点保持书写形态）", () => {
  it("序列化为合法 yaml 且复合节点不展开", () => {
    const text = serializeTree(fullTree());
    const data = load(text);
    // 行为树文档必须是 yaml 顶层映射（dict，契约 §4.1）；Sequence 根 →
    // { Sequence: [...] }
    expect(Array.isArray(data)).toBe(false);
    expect(typeof data === "object" && data !== null).toBe(true);
    const seq = (data as Record<string, unknown>).Sequence as unknown[];
    expect(seq).toHaveLength(6);
    const step = seq[0] as Record<string, unknown>;
    expect(step.Step).toBeTruthy();
    // 复合节点保持书写形态：展开后的 Action/Condition/Selector/Repeat 不应出现
    expect(text).not.toContain("Action");
    expect(text).not.toContain("Condition");
    expect(text).not.toContain("Selector");
    expect(text).not.toContain("Repeat");
  });

  it("往返一致：serialize → parse 结构等价", () => {
    const original = fullTree();
    const text = serializeTree(original);
    const parsed = parseTree(text);
    expect(stripIds(parsed)).toEqual(stripIds(original));
  });

  it("Retry 的 body 与 Branch 的 branches 往返一致", () => {
    const original = fullTree();
    const parsed = parseTree(serializeTree(original));
    const seq = parsed.children;
    const branch = seq[1];
    expect(branch.type).toBe("Branch");
    expect(branch.children).toHaveLength(2);
    expect(branch.children[0].fields).toEqual([
      { key: "when", value: "出现\"成功\"" },
      { key: "then", value: "完成流程" },
    ]);
    expect(branch.children[1].fields).toEqual([{ key: "otherwise", value: "终止流程" }]);

    const retry = seq[4];
    expect(retry.type).toBe("Retry");
    expect(retry.children).toHaveLength(1);
    expect(retry.children[0].type).toBe("Step");
  });

  it("加载「block」形式 A 文档自动解包", () => {
    const text = `
block 冒烟流程:
  Sequence:
    - Step:
        action: 点"登录"
        expect: 出现"工作台"
`.trim();
    const parsed = parseTree(text);
    expect(parsed.type).toBe("Sequence");
    expect(parsed.children[0].type).toBe("Step");
  });

  it("空字段不写入 yaml（交给后端 /check 报告缺失）", () => {
    const node = makeNode("Step", [{ key: "action", value: "" }, { key: "expect", value: "ok" }]);
    const text = serializeTree(node);
    expect(text).toContain("expect");
    expect(text).not.toContain("action:");
  });

  it("非复合节点文档解析抛错（引擎基础节点对用户不可见）", () => {
    expect(() => parseTree("Sequence:\n  - Action: 点登录\n")).toThrow(
      /不支持的节点类型/,
    );
  });

  it("空文档解析抛错", () => {
    expect(() => parseTree("   ")).toThrow(/为空/);
  });

  it("nodeToYamlValue 输出可被 M2 接受的形态", () => {
    const root = fullTree();
    const value = nodeToYamlValue(root) as unknown[];
    const step = value[0] as Record<string, Record<string, string>>;
    expect(step.Step.action).toBe("点\"登录\"");
    const branch = value[1] as Record<string, { branches?: unknown[] }>;
    expect(Array.isArray(branch.Branch.branches)).toBe(true);
    const retry = value[4] as Record<string, { body?: Record<string, unknown> }>;
    expect(retry.Retry.body?.Step).toBeTruthy();
  });
});