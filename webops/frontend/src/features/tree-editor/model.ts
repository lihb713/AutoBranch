import { dump, load } from "js-yaml";
import type { EditorField, EditorNode, EditorNodeType } from "../../types/node";

export const COMPOSITE_TYPES: readonly EditorNodeType[] = [
  "Step",
  "Branch",
  "LoopUntil",
  "IfThenElse",
  "Retry",
  "Sequence",
  "ref",
];

export const ALLOWED_EDITOR_TYPES: ReadonlySet<EditorNodeType> = new Set<EditorNodeType>([
  ...COMPOSITE_TYPES,
  "branch",
]);

export type NodeFieldDef = { key: string; label: string; placeholder?: string };

export const NODE_FIELD_DEFS: Record<EditorNodeType, readonly NodeFieldDef[]> = {
  Step: [
    { key: "action", label: "动作 action", placeholder: "如：点击\"登录\"按钮" },
    { key: "expect", label: "验证 expect", placeholder: "如：出现\"工作台\"" },
  ],
  Branch: [{ key: "action", label: "动作 action", placeholder: "如：点击\"登录\"" }],
  LoopUntil: [
    { key: "action", label: "动作 action", placeholder: "如：点击\"下一页\"" },
    { key: "until", label: "终止条件 until", placeholder: "如：出现\"最后一页\"" },
    { key: "max", label: "循环上限 max", placeholder: "如：50" },
  ],
  IfThenElse: [
    { key: "if", label: "判断 if", placeholder: "如：存在\"下载成功\"提示" },
    { key: "then", label: "成立则 then", placeholder: "如：完成流程" },
    { key: "else", label: "否则 else", placeholder: "如：重试下载" },
  ],
  Retry: [{ key: "max", label: "重试上限 max", placeholder: "如：3" }],
  Sequence: [],
  ref: [{ key: "ref", label: "块引用 ref", placeholder: "如：this/登录" }],
  branch: [
    { key: "when", label: "条件 when", placeholder: "如：出现\"工作台\"" },
    { key: "then", label: "目标 then", placeholder: "如：导出报表" },
  ],
};

let seq = 0;
export function nextNodeId(): string {
  seq += 1;
  return `node-${Date.now().toString(36)}-${seq}`;
}

export function makeNode(
  type: EditorNodeType,
  fields: EditorField[] = [],
  children: EditorNode[] = [],
): EditorNode {
  return { id: nextNodeId(), type, fields, children };
}

export function fieldValue(node: EditorNode, key: string): string {
  const field = node.fields.find((f) => f.key === key);
  return field ? field.value : "";
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const NODE_KEYS: ReadonlySet<string> = new Set([
  ...COMPOSITE_TYPES,
  "Action",
  "Condition",
  "Selector",
  "Repeat",
  "Finish",
]);

function canAddChildTo(parentType: EditorNodeType, childType: EditorNodeType): boolean {
  if (parentType === "Sequence" || parentType === "Retry") {
    return COMPOSITE_TYPES.includes(childType);
  }
  if (parentType === "Branch") {
    return childType === "branch";
  }
  return false;
}

function canBeRoot(type: EditorNodeType): boolean {
  return COMPOSITE_TYPES.includes(type);
}

// ------------------------------------------------------------- 树操作（不可变）

function updateNodeInTree(node: EditorNode, id: string, patch: Partial<EditorNode>): EditorNode {
  if (node.id === id) {
    return { ...node, ...patch };
  }
  return { ...node, children: node.children.map((c) => updateNodeInTree(c, id, patch)) };
}

function findNode(node: EditorNode | null, id: string): EditorNode | null {
  if (node === null) return null;
  if (node.id === id) return node;
  for (const child of node.children) {
    const hit = findNode(child, id);
    if (hit) return hit;
  }
  return null;
}

export function findNodeById(root: EditorNode | null, id: string): EditorNode | null {
  return findNode(root, id);
}

function removeNodeFromTree(node: EditorNode, id: string): EditorNode | null {
  if (node.id === id) return null;
  const children: EditorNode[] = [];
  for (const child of node.children) {
    const removed = removeNodeFromTree(child, id);
    if (removed !== null) children.push(removed);
  }
  return { ...node, children };
}

function insertChild(node: EditorNode, parentId: string, child: EditorNode): EditorNode {
  if (node.id === parentId) {
    return { ...node, children: [...node.children, child] };
  }
  return { ...node, children: node.children.map((c) => insertChild(c, parentId, child)) };
}

function moveNodeInTree(
  node: EditorNode,
  id: string,
  targetParentId: string | null,
): EditorNode | null {
  const target = findNode(node, id);
  if (!target) return node;
  const detached = removeNodeFromTree(node, id);
  if (detached === null) return null;
  if (targetParentId === null) return target;
  const parent = findNode(detached, targetParentId);
  if (!parent || !canAddChildTo(parent.type, target.type)) {
    return node;
  }
  return insertChild(detached, targetParentId, target);
}

// ------------------------------------------------------------- reducer

export type TreeAction =
  | { type: "loadTree"; root: EditorNode | null }
  | { type: "addNode"; parentId: string | null; node: EditorNode }
  | { type: "updateNode"; id: string; patch: Partial<EditorNode> }
  | { type: "setField"; id: string; key: string; value: string }
  | { type: "removeNode"; id: string }
  | { type: "moveNode"; id: string; targetParentId: string | null };

export type EditorState = { root: EditorNode | null };

export const initialEditorState: EditorState = { root: null };

export function treeReducer(state: EditorState, action: TreeAction): EditorState {
  switch (action.type) {
    case "loadTree":
      return { root: action.root };
    case "addNode": {
      if (!ALLOWED_EDITOR_TYPES.has(action.node.type)) {
        return state;
      }
      if (action.parentId === null) {
        if (!canBeRoot(action.node.type)) {
          return state;
        }
        return { root: action.node };
      }
      const parent = findNode(state.root, action.parentId);
      if (!parent || !canAddChildTo(parent.type, action.node.type) || !state.root) {
        return state;
      }
      if (parent.type === "Retry") {
        const body = updateNodeInTree(state.root, action.parentId, {
          children: [action.node],
        });
        return { root: body };
      }
      return { root: state.root ? insertChild(state.root, action.parentId, action.node) : state.root };
    }
    case "updateNode": {
      if (!state.root) return state;
      const existing = findNode(state.root, action.id);
      if (!existing) return state;
      return { root: updateNodeInTree(state.root, action.id, action.patch) };
    }
    case "setField": {
      if (!state.root) return state;
      const existing = findNode(state.root, action.id);
      if (!existing) return state;
      const fields = existing.fields.some((f) => f.key === action.key)
        ? existing.fields.map((f) => (f.key === action.key ? { ...f, value: action.value } : f))
        : [...existing.fields, { key: action.key, value: action.value }];
      return { root: updateNodeInTree(state.root, action.id, { fields }) };
    }
    case "removeNode": {
      if (!state.root) return state;
      if (state.root.id === action.id) return { root: null };
      return { root: removeNodeFromTree(state.root, action.id) };
    }
    case "moveNode": {
      if (!state.root || !findNode(state.root, action.id)) return state;
      return { root: moveNodeInTree(state.root, action.id, action.targetParentId) };
    }
    default:
      return state;
  }
}

// ------------------------------------------------------------- yaml 序列化 / 解析

function fieldMap(fields: EditorField[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of fields) {
    if (f.value.trim() !== "") {
      out[f.key] = f.value;
    }
  }
  return out;
}

function coerceScalar(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (isRecord(value)) {
    for (const key of ["描述", "desc", "条件", "目标", "对象", "谓词", "比较"]) {
      const v = value[key];
      if (typeof v === "string") return v;
    }
    return "";
  }
  return "";
}

function toFields(entries: Record<string, unknown>, order: readonly NodeFieldDef[]): EditorField[] {
  return order
    .filter((def) => def.key in entries)
    .map((def) => ({ key: def.key, value: coerceScalar(entries[def.key]) }));
}

export function nodeToYamlEntry(node: EditorNode): Record<string, unknown> {
  return { [node.type]: nodeToYamlValue(node) };
}

export function nodeToYamlValue(node: EditorNode): unknown {
  switch (node.type) {
    case "Step":
    case "LoopUntil":
    case "IfThenElse":
      return fieldMap(node.fields);
    case "Branch": {
      const m: Record<string, unknown> = { ...fieldMap(node.fields) };
      if (node.children.length > 0) {
        m.branches = node.children.map((c) => nodeToYamlValue(c));
      }
      return m;
    }
    case "Retry": {
      const m: Record<string, unknown> = { ...fieldMap(node.fields) };
      if (node.children.length > 0) {
        m.body = nodeToYamlEntry(node.children[0]);
      }
      return m;
    }
    case "Sequence":
      return node.children.map((c) => nodeToYamlEntry(c));
    case "ref":
      return fieldValue(node, "ref");
    case "branch": {
      if (node.fields.some((f) => f.key === "otherwise")) {
        return { otherwise: fieldValue(node, "otherwise") };
      }
      return { when: fieldValue(node, "when"), then: fieldValue(node, "then") };
    }
  }
}

export function serializeTree(root: EditorNode | null): string {
  if (!root) return "";
  // 统一以「节点键映射」序列化（单节点 → {Step: {...}}；Sequence 根 →
  // {Sequence: [...]}）。行为树文档必须是 yaml 顶层映射（dict，契约 §4.1），
  // 不能直接 dump 数组（顶层序列会被后端 M2 拒绝）。
  const value = nodeToYamlEntry(root);
  return dump(value, { noRefs: true, lineWidth: -1 }).trimEnd() + "\n";
}

function nodeFromYaml(value: unknown): EditorNode {
  if (Array.isArray(value)) {
    return makeNode("Sequence", [], value.map(nodeFromYaml));
  }
  if (!isRecord(value)) {
    throw new Error("行为树节点必须是映射或列表");
  }
  const nodeKeys = Object.keys(value).filter((k) => NODE_KEYS.has(k));
  if (nodeKeys.length !== 1) {
    throw new Error(`节点项必须含且仅含一个节点键（实际: ${Object.keys(value).join(", ")}）`);
  }
  const key = nodeKeys[0];
  const body = value[key];
  switch (key) {
    case "Step":
    case "LoopUntil":
    case "IfThenElse":
      return makeNode(key, toFields(isRecord(body) ? body : {}, NODE_FIELD_DEFS[key]), []);
    case "ref":
      return makeNode("ref", [{ key: "ref", value: coerceScalar(body) }], []);
    case "Branch": {
      if (!isRecord(body)) throw new Error("Branch 的值必须是映射");
      const fields = toFields(body, NODE_FIELD_DEFS.Branch);
      const children = Array.isArray(body.branches) ? body.branches.map(branchFromYaml) : [];
      return makeNode("Branch", fields, children);
    }
    case "Retry": {
      if (!isRecord(body)) throw new Error("Retry 的值必须是映射");
      const fields = toFields(body, NODE_FIELD_DEFS.Retry);
      const children = body.body !== undefined ? [nodeFromYaml(body.body)] : [];
      return makeNode("Retry", fields, children);
    }
    case "Sequence": {
      const children =
        Array.isArray(body) ? body.map(nodeFromYaml) : body !== undefined ? [nodeFromYaml(body)] : [];
      return makeNode("Sequence", [], children);
    }
    default:
      throw new Error(`文档包含前端不支持的节点类型 '${key}'（引擎基础节点对用户不可见）`);
  }
}

function branchFromYaml(item: unknown): EditorNode {
  if (!isRecord(item)) {
    throw new Error("Branch 的 branches 项必须是映射");
  }
  if ("when" in item) {
    return makeNode(
      "branch",
      [
        { key: "when", value: coerceScalar(item.when) },
        { key: "then", value: coerceScalar(item.then) },
      ],
      [],
    );
  }
  return makeNode("branch", [{ key: "otherwise", value: coerceScalar(item.otherwise) }], []);
}

export function parseTree(yamlText: string): EditorNode {
  if (!yamlText.trim()) {
    throw new Error("行为树文档为空");
  }
  let data: unknown;
  try {
    data = load(yamlText);
  } catch (err) {
    throw new Error(`yaml 解析失败: ${(err as Error).message}`);
  }
  if (isRecord(data)) {
    const blockKeys = Object.keys(data).filter((k) => k.startsWith("操作块 "));
    if (blockKeys.length === 1 && Object.keys(data).length === 1) {
      data = data[blockKeys[0]];
    } else if (blockKeys.length > 0) {
      throw new Error("该文档含多个操作块定义，暂不支持在编辑器中展示");
    }
  }
  return nodeFromYaml(data);
}