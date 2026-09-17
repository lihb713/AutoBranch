import { dump, load } from "js-yaml";

/** 统一槽位模型节点类型（契约 §12：一文档一树 + 语义槽位字段）。 */
export type NodeType =
  | "Action"
  | "Step"
  | "Root"
  | "Sequence"
  | "IfThenElse"
  | "Branch"
  | "Retry"
  | "LoopUntil"
  | "ref"
  | "FunctionCall";

/** Branch 的分支行：{when, action: id} 或 {otherwise: id}（otherwise 值即槽位引用）。 */
export type BranchRow = {
  when?: string;
  action?: string;
  otherwise?: string;
};

/** 节点对象池中的单个节点。
 *
 * 槽位字段按类型（值=子树根 id）：Root.body / Sequence.actions /
 * Step.action / IfThenElse.then+else / Branch.action+branches[].action /
 * Retry.body / LoopUntil.action。条件（expect/if/when/until）与
 * description/max 等标量存于 fields。
 */
export type TreeNode = {
  id: string;
  type: NodeType;
  name: string;
  fields: Record<string, string>;
  body?: string;
  actions?: string[];
  action?: string;
  then?: string;
  else?: string;
  branches?: BranchRow[];
  target?: string;
  function?: string;
  args?: string[];
  returns?: Record<string, string>;
};

/** 一份行为树文档（自包含：tree/nodes/root + 文档级接口与配置）。 */
export type TreeDoc = {
  tree: string;
  inputs: Record<string, string>;
  outputs: string[];
  config: Record<string, unknown>;
  nodes: Record<string, TreeNode>;
  root: string;
};

/** 一个挂载点（槽位）：字段 + 标签 + 引用的子 id。 */
export type SlotMount = {
  field: string;
  label: string;
  childId: string | null;
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** 生成未占用的节点 id（n1/n2...，跳过已占用）。 */
export function nextNodeId(nodes: Record<string, TreeNode>): string {
  let i = 1;
  while (`n${i}` in nodes) i += 1;
  return `n${i}`;
}

/** 新建节点（默认名=类型名；Step 自动附带 Action 子节点挂入 action 槽位）。 */
export function makeNode(
  type: NodeType,
  id: string,
  _nodes: Record<string, TreeNode>,
  name?: string,
): TreeNode {
  const node: TreeNode = {
    id,
    type,
    name: name ?? type,
    fields: {},
  };
  if (type === "ref") {
    node.target = "";
    node.args = [];
    node.returns = {};
  }
  if (type === "FunctionCall") {
    node.function = "";
    node.args = [];
    node.returns = {};
  }
  if (type === "Sequence") node.actions = [];
  if (type === "Branch") {
    node.branches = [];
  }
  return node;
}

/** 节点的全部挂载点（统一槽位抽象：布局/游离判定/删除语义基于它）。 */
export function slotFields(node: TreeNode): SlotMount[] {
  switch (node.type) {
    case "Root":
      return [{ field: "body", label: "主体", childId: node.body ?? null }];
    case "Sequence":
      return (node.actions ?? []).map((c, i) => ({
        field: "actions",
        label: `动作 ${i + 1}`,
        childId: c,
      }));
    case "Step":
      return [{ field: "action", label: "操作", childId: node.action ?? null }];
    case "IfThenElse":
      return [
        { field: "then", label: "成立", childId: node.then ?? null },
        { field: "else", label: "否则", childId: node.else ?? null },
      ];
    case "Branch": {
      const mounts: SlotMount[] = [
        { field: "action", label: "前置操作", childId: node.action ?? null },
      ];
      (node.branches ?? []).forEach((b, i) => {
        mounts.push({
          field: "branches",
          label: `分支 ${i + 1}${b.when ? `（${b.when}）` : "（otherwise）"}`,
          childId: (b.action ?? b.otherwise) || null,
        });
      });
      return mounts;
    }
    case "Retry":
      return [{ field: "body", label: "重试体", childId: node.body ?? null }];
    case "LoopUntil":
      return [{ field: "action", label: "循环体", childId: node.action ?? null }];
    default:
      return [];
  }
}

/** 引用计数：某节点被哪些槽位引用（游离判定/重复引用校验用）。 */
export function referencedIds(doc: TreeDoc): Set<string> {
  const refs = new Set<string>();
  for (const node of Object.values(doc.nodes)) {
    for (const m of slotFields(node)) {
      if (m.childId) refs.add(m.childId);
    }
  }
  return refs;
}

/** 游离树根：未被任何槽位引用、且非文档 root 的节点 id。 */
export function freeRoots(doc: TreeDoc): string[] {
  const refs = referencedIds(doc);
  return Object.keys(doc.nodes).filter((id) => !refs.has(id) && id !== doc.root);
}

const CONFIG_KEYS = ["timeout", "retry", "browser"];
const SLOT_KEYS = ["body", "actions", "action", "then", "else", "branches"];
const REF_KEYS = ["target", "args", "returns"];
const SKIP_KEYS = new Set([...SLOT_KEYS, ...REF_KEYS, "function", "type", "name", "id"]);

/** 从文档 dict 解析为 TreeDoc（统一槽位 DSL）。 */
export function parseDoc(yamlText: string): TreeDoc {
  const data = load(yamlText);
  if (!isRecord(data)) throw new Error("文档必须是 yaml 顶层映射");
  const tree = data["tree"];
  if (typeof tree !== "string" || !tree.trim()) throw new Error("缺少 tree 顶层键");
  const nodesRaw = data["nodes"];
  if (!isRecord(nodesRaw)) throw new Error("缺少 nodes 节点池");
  const root = data["root"];
  if (typeof root !== "string" || !root) throw new Error("缺少 root 引用");

  const nodes: Record<string, TreeNode> = {};
  for (const [id, body] of Object.entries(nodesRaw)) {
    if (!isRecord(body)) throw new Error(`节点 '${id}' 不是映射`);
    const type = body["type"];
    if (typeof type !== "string") throw new Error(`节点 '${id}' 缺少 type`);
    const node: TreeNode = {
      id,
      type: type as NodeType,
      name: typeof body["name"] === "string" ? (body["name"] as string) : (type as string),
      fields: {},
    };
    if (typeof body["body"] === "string") node.body = body["body"];
    if (Array.isArray(body["actions"])) {
      node.actions = body["actions"].filter((v): v is string => typeof v === "string");
    }
    if (typeof body["action"] === "string") node.action = body["action"];
    if (typeof body["then"] === "string") node.then = body["then"];
    if (typeof body["else"] === "string") node.else = body["else"];
    if (Array.isArray(body["branches"])) {
      node.branches = body["branches"].map((b) => {
        if (!isRecord(b)) return { otherwise: "" };
        const row: BranchRow = {};
        if (typeof b["when"] === "string") row.when = b["when"];
        if (typeof b["action"] === "string") row.action = b["action"];
        if (typeof b["otherwise"] === "string") row.otherwise = b["otherwise"];
        return row;
      });
    }
    if (type === "ref") {
      node.target = typeof body["target"] === "string" ? (body["target"] as string) : "";
      node.args = Array.isArray(body["args"]) ? body["args"].map(String) : [];
      node.returns = isRecord(body["returns"])
        ? Object.fromEntries(Object.entries(body["returns"]).map(([k, v]) => [k, String(v)]))
        : {};
    }
    if (type === "FunctionCall") {
      node.function = typeof body["function"] === "string" ? (body["function"] as string) : "";
      node.args = Array.isArray(body["args"]) ? body["args"].map(String) : [];
      node.returns = isRecord(body["returns"])
        ? Object.fromEntries(Object.entries(body["returns"]).map(([k, v]) => [k, String(v)]))
        : {};
    }
    for (const [k, v] of Object.entries(body)) {
      if (SKIP_KEYS.has(k)) continue;
      node.fields[k] = String(v);
    }
    nodes[id] = node;
  }
  return {
    tree: tree.trim(),
    inputs: isRecord(data["inputs"])
      ? Object.fromEntries(Object.entries(data["inputs"]).map(([k, v]) => [k, String(v)]))
      : {},
    outputs: Array.isArray(data["outputs"]) ? data["outputs"].map(String) : [],
    config: Object.fromEntries(CONFIG_KEYS.filter((k) => k in data).map((k) => [k, data[k]])),
    nodes,
    root,
  };
}

/** 把 TreeDoc 序列化为 yaml 文本（统一槽位 DSL）。 */
export function serializeDoc(doc: TreeDoc): string {
  const out: Record<string, unknown> = { tree: doc.tree };
  if (Object.keys(doc.inputs).length > 0) out["inputs"] = doc.inputs;
  if (doc.outputs.length > 0) out["outputs"] = doc.outputs;
  for (const [k, v] of Object.entries(doc.config)) out[k] = v;
  const nodes: Record<string, unknown> = {};
  for (const [id, node] of Object.entries(doc.nodes)) {
    const body: Record<string, unknown> = { type: node.type, name: node.name };
    if (node.body) body["body"] = node.body;
    if (node.actions && node.actions.length > 0) body["actions"] = node.actions.filter(Boolean);
    if (node.action) body["action"] = node.action;
    if (node.then) body["then"] = node.then;
    if (node.else) body["else"] = node.else;
    if (node.branches && node.branches.length > 0) body["branches"] = node.branches;
    for (const [k, v] of Object.entries(node.fields)) {
      if (v !== "") body[k] = v;
    }
    if (node.type === "ref") {
      body["target"] = node.target ?? "";
      if (node.args && node.args.length > 0) body["args"] = node.args;
      if (node.returns && Object.keys(node.returns).length > 0) body["returns"] = node.returns;
    }
    if (node.type === "FunctionCall") {
      body["function"] = node.function ?? "";
      if (node.args && node.args.length > 0) body["args"] = node.args;
      if (node.returns && Object.keys(node.returns).length > 0) body["returns"] = node.returns;
    }
    nodes[id] = body;
  }
  out["nodes"] = nodes;
  out["root"] = doc.root;
  return dump(out, { noRefs: true, lineWidth: -1 }).trimEnd() + "\n";
}

// ---------------------------------------------------------------- 删除/修改语义

function cloneDoc(doc: TreeDoc): TreeDoc {
  return JSON.parse(JSON.stringify(doc)) as TreeDoc;
}

/** 删除槽位 = 解引用：清空该挂载点引用（branches 挂载点=移除该分支行）。 */
export function detachSlot(doc: TreeDoc, parentId: string, slotIndex: number): TreeDoc {
  const next = cloneDoc(doc);
  const parent = next.nodes[parentId];
  if (!parent) return next;
  const mounts = slotFields(parent);
  const target = mounts[slotIndex];
  if (!target) return next;
  if (target.field === "body") delete parent.body;
  else if (target.field === "action") delete parent.action;
  else if (target.field === "then") delete parent.then;
  else if (target.field === "else") delete parent.else;
  else if (target.field === "actions") {
    parent.actions = (parent.actions ?? []).filter((_, i) => i !== slotIndex);
  } else if (target.field === "branches") {
    const bi = slotIndex - (parent.action ? 1 : 0);
    parent.branches = (parent.branches ?? []).filter((_, i) => i !== bi);
  }
  return next;
}

/** 修改槽位：旧节点回游离区、新节点（游离树根）入该挂载点。 */
export function setSlot(doc: TreeDoc, parentId: string, slotIndex: number, childId: string): TreeDoc {
  const next = cloneDoc(doc);
  const parent = next.nodes[parentId];
  if (!parent || childId === parentId || !(childId in next.nodes)) return next;
  const mounts = slotFields(parent);
  const target = mounts[slotIndex];
  if (!target) return next;
  if (target.field === "body") parent.body = childId;
  else if (target.field === "action") parent.action = childId;
  else if (target.field === "then") parent.then = childId;
  else if (target.field === "else") parent.else = childId;
  else if (target.field === "actions") {
    parent.actions = (parent.actions ?? []).map((c, i) => (i === slotIndex ? childId : c));
  } else if (target.field === "branches") {
    const bi = slotIndex - (parent.action ? 1 : 0);
    const row = parent.branches?.[bi];
    if (row) {
      row.action = childId;
      if (row.otherwise) delete row.otherwise;
    }
  }
  return next;
}

/** 删除单节点（不含后代）：其各槽位子树各自成为独立游离树；根不可删除 → null。 */
export function removeNode(doc: TreeDoc, id: string): TreeDoc | null {
  if (id === doc.root) return null;
  const next = cloneDoc(doc);
  if (!(id in next.nodes)) return next;
  for (const p of Object.values(next.nodes)) {
    if (p.body === id) delete p.body;
    if (p.action === id) delete p.action;
    if (p.then === id) delete p.then;
    if (p.else === id) delete p.else;
    if (p.actions) p.actions = p.actions.filter((c) => c !== id);
    if (p.branches) {
      p.branches = p.branches
        .filter((b) => (b.action ?? b.otherwise) !== id)
        .map((b) => ({ ...b }));
    }
  }
  delete next.nodes[id];
  return next;
}

/** 删除子树：节点 + 全部后代一并删除；根不可删除 → null。 */
export function deleteSubtree(doc: TreeDoc, id: string): TreeDoc | null {
  if (id === doc.root) return null;
  const next = cloneDoc(doc);
  if (!(id in next.nodes)) return next;
  const doomed = new Set<string>();
  const collect = (nid: string): void => {
    if (doomed.has(nid)) return;
    doomed.add(nid);
    const n = next.nodes[nid];
    if (!n) return;
    for (const m of slotFields(n)) {
      if (m.childId) collect(m.childId);
    }
  };
  collect(id);
  for (const p of Object.values(next.nodes)) {
    if (p.body && doomed.has(p.body)) delete p.body;
    if (p.action && doomed.has(p.action)) delete p.action;
    if (p.then && doomed.has(p.then)) delete p.then;
    if (p.else && doomed.has(p.else)) delete p.else;
    if (p.actions) p.actions = p.actions.filter((c) => !doomed.has(c));
    if (p.branches) {
      p.branches = p.branches
        .filter((b) => !doomed.has(b.action ?? b.otherwise ?? ""))
        .map((b) => ({ ...b }));
    }
  }
  for (const d of doomed) delete next.nodes[d];
  return next;
}

/** 创建 Step 节点并自动附带一个 Action 子节点挂入其 action 槽位。 */
export function createStepWithAction(doc: TreeDoc): { doc: TreeDoc; stepId: string } {
  const stepId = nextNodeId(doc.nodes);
  const actionId = nextNodeId({ ...doc.nodes, [stepId]: { id: stepId } as TreeNode });
  const next = cloneDoc(doc);
  next.nodes[actionId] = makeNode("Action", actionId, next.nodes, "操作");
  next.nodes[stepId] = makeNode("Step", stepId, next.nodes, "步骤");
  next.nodes[stepId].action = actionId;
  return { doc: next, stepId };
}