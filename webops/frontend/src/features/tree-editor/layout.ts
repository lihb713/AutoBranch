import { slotFields, type TreeDoc, type TreeNode } from "./treeModel";

/** 布局常量：固定尺寸节点卡片（画布不显示字段详情）。 */
export const NODE_W = 160;
export const NODE_H = 48;
export const GAP_X = 28;
export const GAP_Y = 56;
/** 游离树之间的间距。 */
export const TREE_GAP = 64;

export type Box = { id: string; x: number; y: number };

export type LayoutResult = {
  boxes: Map<string, Box>;
  width: number;
  height: number;
};

type Subtree = {
  width: number;
  height: number;
  centerX: number;
};

type ChildIdsFn = (node: TreeNode) => string[];

/** 把预览树节点前缀化注入（ref 展开并入主树布局，避免与主树重叠）。
 * 节点 id 映射为 ``<prefix><id>``，槽位引用同步重映射。
 */
export function prefixTree(preview: TreeDoc, prefix: string): Record<string, TreeNode> {
  const out: Record<string, TreeNode> = {};
  const map = (id: string) => `${prefix}${id}`;
  for (const [id, node] of Object.entries(preview.nodes)) {
    const copy: TreeNode = { ...node, id: map(id) };
    if (copy.body) copy.body = map(copy.body);
    if (copy.action) copy.action = map(copy.action);
    if (copy.then) copy.then = map(copy.then);
    if (copy.else) copy.else = map(copy.else);
    if (copy.actions) copy.actions = copy.actions.map(map);
    if (copy.branches) {
      copy.branches = copy.branches.map((b) => ({
        ...b,
        action: b.action ? map(b.action) : b.action,
        otherwise: b.otherwise ? map(b.otherwise) : b.otherwise,
      }));
    }
    out[map(id)] = copy;
  }
  return out;
}

/** 递归计算子树包围盒（自底向上算宽、自顶向下定位）。 */
function measure(id: string, nodes: Record<string, TreeNode>, childIdsOf: ChildIdsFn, seen: Set<string>): Subtree {
  const node = nodes[id];
  if (!node || seen.has(id)) {
    return { width: NODE_W, height: NODE_H, centerX: NODE_W / 2 };
  }
  const children = childIdsOf(node).filter((c) => c in nodes && !seen.has(c));
  if (children.length === 0) {
    return { width: NODE_W, height: NODE_H, centerX: NODE_W / 2 };
  }
  const subSeen = new Set(seen);
  subSeen.add(id);
  const subs = children.map((c) => measure(c, nodes, childIdsOf, subSeen));
  const totalChildW = subs.reduce((s, b) => s + b.width, 0) + GAP_X * (children.length - 1);
  const width = Math.max(NODE_W, totalChildW);
  const childH = Math.max(...subs.map((s) => s.height));
  const height = NODE_H + GAP_Y + childH;
  return { width, height, centerX: width / 2 };
}

/** 递归定位子树（父在上、子在下、兄弟水平均布）。 */
function place(
  id: string,
  nodes: Record<string, TreeNode>,
  childIdsOf: ChildIdsFn,
  left: number,
  top: number,
  boxes: Map<string, Box>,
  seen: Set<string>,
): void {
  const node = nodes[id];
  if (!node || seen.has(id)) return;
  const sub = measure(id, nodes, childIdsOf, new Set());
  boxes.set(id, { id, x: left + sub.centerX - NODE_W / 2, y: top });
  const children = childIdsOf(node).filter((c) => c in nodes);
  if (children.length === 0) return;
  const subSeen = new Set(seen);
  subSeen.add(id);
  const subs = children.map((c) => measure(c, nodes, childIdsOf, subSeen));
  const totalChildW = subs.reduce((s, b) => s + b.width, 0) + GAP_X * (children.length - 1);
  let cursor = left + (sub.width - totalChildW) / 2;
  for (let i = 0; i < children.length; i += 1) {
    place(children[i], nodes, childIdsOf, cursor, top + NODE_H + GAP_Y, boxes, subSeen);
    cursor += subs[i].width + GAP_X;
  }
}

function layoutTreeInternal(
  rootId: string,
  nodes: Record<string, TreeNode>,
  childIdsOf: ChildIdsFn,
): LayoutResult {
  const boxes = new Map<string, Box>();
  if (!(rootId in nodes)) return { boxes, width: 0, height: 0 };
  const sub = measure(rootId, nodes, childIdsOf, new Set());
  place(rootId, nodes, childIdsOf, 0, 0, boxes, new Set());
  return { boxes, width: sub.width, height: sub.height };
}

/** 布局单棵树（不含 ref 展开预览）。 */
export function layoutTree(
  rootId: string,
  nodes: Record<string, TreeNode>,
): LayoutResult {
  const childIdsOf: ChildIdsFn = (node) =>
    slotFields(node)
      .map((m) => m.childId)
      .filter((c): c is string => c !== null);
  return layoutTreeInternal(rootId, nodes, childIdsOf);
}

/** 布局整份文档：主树在左上，游离树依次排布在主树下方。
 *
 * :param refExpansions: ref 节点 id → 被引文档（展开预览），其整树并入主树布局
 *   （节点 id 以 ``<refId>:`` 前缀隔离，ref → 预览根 视作子节点向下生长）。
 */
export function layoutDocument(
  rootId: string,
  freeRootIds: string[],
  nodes: Record<string, TreeNode>,
  refExpansions: Record<string, TreeDoc> = {},
): LayoutResult {
  const allNodes: Record<string, TreeNode> = { ...nodes };
  const previewRootOf: Record<string, string> = {};
  for (const [refId, preview] of Object.entries(refExpansions)) {
    const prefix = `${refId}:`;
    Object.assign(allNodes, prefixTree(preview, prefix));
    previewRootOf[refId] = `${prefix}${preview.root}`;
  }
  const childIdsOf: ChildIdsFn = (node) => {
    const ids = slotFields(node)
      .map((m) => m.childId)
      .filter((c): c is string => c !== null);
    if (node.type === "ref" && previewRootOf[node.id]) ids.push(previewRootOf[node.id]);
    return ids;
  };

  const main = layoutTreeInternal(rootId, allNodes, childIdsOf);
  const boxes = new Map(main.boxes);
  let y = main.height + TREE_GAP;
  let maxW = main.width;
  for (const fid of freeRootIds) {
    const sub = layoutTreeInternal(fid, allNodes, childIdsOf);
    for (const [id, box] of sub.boxes) {
      boxes.set(id, { id, x: box.x, y: box.y + y });
    }
    y += sub.height + TREE_GAP;
    maxW = Math.max(maxW, sub.width);
  }
  return { boxes, width: maxW, height: y };
}