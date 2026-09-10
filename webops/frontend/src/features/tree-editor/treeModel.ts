import { dump, load } from "js-yaml";

/** 新 DSL 节点类型（契约 §12：一文档一树 + 节点对象池 + 槽位引用）。 */
export type NodeType =
  | "Root"
  | "Step"
  | "Sequence"
  | "IfThenElse"
  | "Branch"
  | "Retry"
  | "LoopUntil"
  | "ref";

/** 容器节点类型（有槽位引用子节点）。 */
export const CONTAINER_TYPES: ReadonlySet<NodeType> = new Set<NodeType>([
  "Root",
  "Sequence",
  "IfThenElse",
  "Branch",
  "Retry",
  "LoopUntil",
]);

/** 节点对象池中的单个节点。 */
export type TreeNode = {
  id: string;
  type: NodeType;
  name: string;
  /** 叶子/复合字段（action/expect/when/then/if/else/max/until...）。 */
  fields: Record<string, string>;
  /** 槽位：有序子节点 id 列表（容器节点；叶子为空）。 */
  slots: string[];
  /** ref 专属：目标文档名（单段）。 */
  target?: string;
  /** ref 专属：实参列表（本树变量名或字面量）。 */
  args?: string[];
  /** ref 专属：接收参数（本树新建参数名 -> 类型）。 */
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

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** 生成未占用的节点 id（n1/n2...，跳过已占用）。 */
export function nextNodeId(nodes: Record<string, TreeNode>): string {
  let i = 1;
  while (`n${i}` in nodes) i += 1;
  return `n${i}`;
}

/** 新建节点（默认名=类型名，容器 slots 空）。 */
export function makeNode(
  type: NodeType,
  id: string,
  name?: string,
): TreeNode {
  const node: TreeNode = {
    id,
    type,
    name: name ?? type,
    fields: {},
    slots: [],
  };
  if (type === "ref") {
    node.target = "";
    node.args = [];
    node.returns = {};
  }
  return node;
}

/** 引用计数：某节点被哪些槽位引用（用于游离判定/重复引用校验）。 */
export function referencedIds(doc: TreeDoc): Set<string> {
  const refs = new Set<string>();
  for (const node of Object.values(doc.nodes)) {
    for (const child of node.slots) refs.add(child);
  }
  return refs;
}

/** 游离树根：未被任何槽位引用、且非文档 root 的节点 id。 */
export function freeRoots(doc: TreeDoc): string[] {
  const refs = referencedIds(doc);
  return Object.keys(doc.nodes).filter((id) => !refs.has(id) && id !== doc.root);
}

const CONFIG_KEYS = ["timeout", "retry", "browser"];

/** 从文档 dict 解析为 TreeDoc（顶层 tree/nodes/root + inputs/outputs/config）。 */
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
      slots: [],
    };
    if (isRecord(body["slots"])) {
      node.slots = Object.values(body["slots"]).filter(
        (v): v is string => typeof v === "string",
      );
    }
    for (const [k, v] of Object.entries(body)) {
      if (["type", "name", "slots", "id", "target", "args", "returns"].includes(k)) continue;
      node.fields[k] = String(v);
    }
    if (type === "ref") {
      node.target = typeof body["target"] === "string" ? (body["target"] as string) : "";
      node.args = Array.isArray(body["args"]) ? body["args"].map(String) : [];
      node.returns = isRecord(body["returns"])
        ? Object.fromEntries(Object.entries(body["returns"]).map(([k, v]) => [k, String(v)]))
        : {};
    }
    nodes[id] = node;
  }
  return {
    tree: tree.trim(),
    inputs: isRecord(data["inputs"])
      ? Object.fromEntries(Object.entries(data["inputs"]).map(([k, v]) => [k, String(v)]))
      : {},
    outputs: Array.isArray(data["outputs"]) ? data["outputs"].map(String) : [],
    config: Object.fromEntries(
      CONFIG_KEYS.filter((k) => k in data).map((k) => [k, data[k]]),
    ),
    nodes,
    root,
  };
}

/** 把 TreeDoc 序列化为 yaml 文本（tree/nodes/root + 接口/配置）。 */
export function serializeDoc(doc: TreeDoc): string {
  const out: Record<string, unknown> = { tree: doc.tree };
  if (Object.keys(doc.inputs).length > 0) out["inputs"] = doc.inputs;
  if (doc.outputs.length > 0) out["outputs"] = doc.outputs;
  for (const [k, v] of Object.entries(doc.config)) out[k] = v;
  const nodes: Record<string, unknown> = {};
  for (const [id, node] of Object.entries(doc.nodes)) {
    const body: Record<string, unknown> = { type: node.type, name: node.name };
    for (const [k, v] of Object.entries(node.fields)) {
      if (v !== "") body[k] = v;
    }
    if (CONTAINER_TYPES.has(node.type) && node.slots.length > 0) {
      body["slots"] = Object.fromEntries(node.slots.map((c, i) => [String(i + 1), c]));
    }
    if (node.type === "ref") {
      body["target"] = node.target ?? "";
      if (node.args && node.args.length > 0) body["args"] = node.args;
      if (node.returns && Object.keys(node.returns).length > 0) body["returns"] = node.returns;
    }
    nodes[id] = body;
  }
  out["nodes"] = nodes;
  out["root"] = doc.root;
  return dump(out, { noRefs: true, lineWidth: -1 }).trimEnd() + "\n";
}