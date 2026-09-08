import { describe, expect, it } from "vitest";
import type { EditorNode } from "../../types/node";
import {
  findNodeById,
  initialEditorState,
  makeNode,
  serializeTree,
  treeReducer,
} from "./model";

function step(action = "点\"登录\"", expect_ = "出现\"工作台\""): EditorNode {
  return makeNode("Step", [
    { key: "action", value: action },
    { key: "expect", value: expect_ },
  ]);
}

describe("treeReducer 节点树操作", () => {
  it("addNode 无父节点 → 设为根", () => {
    const state = treeReducer(initialEditorState, { type: "addNode", parentId: null, node: step() });
    expect(state.root?.type).toBe("Step");
  });

  it("addNode 到 Sequence 下 → 追加子节点", () => {
    const seq = makeNode("Sequence", [], [step()]);
    let state = treeReducer(initialEditorState, { type: "addNode", parentId: null, node: seq });
    const child = step("点\"退出\"");
    state = treeReducer(state, { type: "addNode", parentId: seq.id, node: child });
    expect(findNodeById(state.root, seq.id)?.children).toHaveLength(2);
  });

  it("addNode 拒绝非法类型（引擎基础节点不可见）", () => {
    const bad = makeNode("Action" as never, [{ key: "action", value: "x" }]);
    let state = treeReducer(initialEditorState, { type: "addNode", parentId: null, node: bad });
    expect(state.root).toBeNull();

    const seq = makeNode("Sequence", [], []);
    state = treeReducer(state, { type: "addNode", parentId: null, node: seq });
    const alsoBad = makeNode("Foo" as never, []);
    state = treeReducer(state, { type: "addNode", parentId: seq.id, node: alsoBad });
    expect(findNodeById(state.root, seq.id)?.children).toHaveLength(0);
  });

  it("addNode 到 Branch 下只允许分支行", () => {
    const branch = makeNode("Branch", [{ key: "action", value: "a" }], []);
    let state = treeReducer(initialEditorState, { type: "addNode", parentId: null, node: branch });
    const compositeChild = step();
    state = treeReducer(state, { type: "addNode", parentId: branch.id, node: compositeChild });
    expect(findNodeById(state.root, branch.id)?.children).toHaveLength(0);

    const row = makeNode("branch", [
      { key: "when", value: "出现\"工作台\"" },
      { key: "then", value: "导出报表" },
    ]);
    state = treeReducer(state, { type: "addNode", parentId: branch.id, node: row });
    expect(findNodeById(state.root, branch.id)?.children).toHaveLength(1);
  });

  it("addNode 到 Retry 下替换为唯一 body", () => {
    const retry = makeNode("Retry", [{ key: "max", value: "3" }], []);
    let state = treeReducer(initialEditorState, { type: "addNode", parentId: null, node: retry });
    const body1 = step("尝试1");
    const body2 = step("尝试2");
    state = treeReducer(state, { type: "addNode", parentId: retry.id, node: body1 });
    state = treeReducer(state, { type: "addNode", parentId: retry.id, node: body2 });
    expect(findNodeById(state.root, retry.id)?.children).toHaveLength(1);
    expect(serializeTree(state.root)).toContain("尝试2");
  });

  it("updateNode / setField 更新字段", () => {
    let state = treeReducer(initialEditorState, { type: "addNode", parentId: null, node: step() });
    const rootId = state.root!.id;
    state = treeReducer(state, { type: "setField", id: rootId, key: "expect", value: "出现\"列表\"" });
    expect(findNodeById(state.root, rootId)?.fields[1].value).toBe("出现\"列表\"");
  });

  it("removeNode 删除根与子节点", () => {
    let state = treeReducer(initialEditorState, { type: "addNode", parentId: null, node: step() });
    const rootId = state.root!.id;
    state = treeReducer(state, { type: "removeNode", id: rootId });
    expect(state.root).toBeNull();

    const seq = makeNode("Sequence", [], [step("a"), step("b")]);
    state = treeReducer(state, { type: "addNode", parentId: null, node: seq });
    const first = seq.children[0];
    state = treeReducer(state, { type: "removeNode", id: first.id });
    expect(findNodeById(state.root, seq.id)?.children).toHaveLength(1);
  });

  it("moveNode 迁移到目标父节点下", () => {
    const seqA = makeNode("Sequence", [], [step("a")]);
    const seqB = makeNode("Sequence", [], [step("b")]);
    const root = makeNode("Sequence", [], [seqA, seqB]);
    let state = treeReducer(initialEditorState, { type: "addNode", parentId: null, node: root });
    const moving = seqA.children[0];
    state = treeReducer(state, { type: "moveNode", id: moving.id, targetParentId: seqB.id });
    expect(findNodeById(state.root, seqA.id)?.children).toHaveLength(0);
    expect(findNodeById(state.root, seqB.id)?.children).toHaveLength(2);
  });

  it("loadTree 整体替换", () => {
    const root = makeNode("LoopUntil", [
      { key: "action", value: "点击下一页" },
      { key: "until", value: "出现最后一页" },
      { key: "max", value: "50" },
    ]);
    const state = treeReducer(initialEditorState, { type: "loadTree", root });
    expect(state.root?.type).toBe("LoopUntil");
  });
});