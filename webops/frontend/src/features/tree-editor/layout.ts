import { slotFields, type TreeNode } from "./treeModel";

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
  /** 子树占位宽度（含子孙）。 */
  width: number;
  /** 子树占位高度（含子孙）。 */
  height: number;
  /** 相对布局：节点中心 x 相对子树左边缘的偏移。 */
  centerX: number;
};

function childIds(node: TreeNode): string[] {
  return slotFields(node)
    .map((m) => m.childId)
    .filter((c): c is string => c !== null);
}

/** 递归计算子树包围盒（自底向上算宽、自顶向下定位）。 */
function measure(id: string, nodes: Record<string, TreeNode>, seen: Set<string>): Subtree {
  const node = nodes[id];
  if (!node || seen.has(id)) {
    return { width: NODE_W, height: NODE_H, centerX: NODE_W / 2 };
  }
  const children = childIds(node).filter((c) => c in nodes && !seen.has(c));
  if (children.length === 0) {
    return { width: NODE_W, height: NODE_H, centerX: NODE_W / 2 };
  }
  const subSeen = new Set(seen);
  subSeen.add(id);
  const subs = children.map((c) => measure(c, nodes, subSeen));
  const totalChildW =
    subs.reduce((s, b) => s + b.width, 0) + GAP_X * (children.length - 1);
  const width = Math.max(NODE_W, totalChildW);
  const childH = Math.max(...subs.map((s) => s.height));
  const height = NODE_H + GAP_Y + childH;
  return { width, height, centerX: width / 2 };
}

/** 递归定位子树（父在上、子在下、兄弟水平均布）。 */
function place(
  id: string,
  nodes: Record<string, TreeNode>,
  left: number,
  top: number,
  boxes: Map<string, Box>,
  seen: Set<string>,
): void {
  const node = nodes[id];
  if (!node || seen.has(id)) return;
  const sub = measure(id, nodes, new Set());
  boxes.set(id, { id, x: left + sub.centerX - NODE_W / 2, y: top });
  const children = childIds(node).filter((c) => c in nodes);
  if (children.length === 0) return;
  const subSeen = new Set(seen);
  subSeen.add(id);
  const subs = children.map((c) => measure(c, nodes, subSeen));
  const totalChildW = subs.reduce((s, b) => s + b.width, 0) + GAP_X * (children.length - 1);
  let cursor = left + (sub.width - totalChildW) / 2;
  for (let i = 0; i < children.length; i += 1) {
    place(children[i], nodes, cursor, top + NODE_H + GAP_Y, boxes, subSeen);
    cursor += subs[i].width + GAP_X;
  }
}

/** 布局一棵树（根在上、向下生长、兄弟水平）。 */
export function layoutTree(
  rootId: string,
  nodes: Record<string, TreeNode>,
): LayoutResult {
  const boxes = new Map<string, Box>();
  if (!(rootId in nodes)) return { boxes, width: 0, height: 0 };
  const sub = measure(rootId, nodes, new Set());
  place(rootId, nodes, 0, 0, boxes, new Set());
  return { boxes, width: sub.width, height: sub.height };
}

/** 布局整份文档：主树在左上，游离树依次排布在主树下方。 */
export function layoutDocument(
  rootId: string,
  freeRootIds: string[],
  nodes: Record<string, TreeNode>,
): LayoutResult {
  const main = layoutTree(rootId, nodes);
  const boxes = new Map(main.boxes);
  let y = main.height + TREE_GAP;
  let maxW = main.width;
  for (const fid of freeRootIds) {
    const sub = layoutTree(fid, nodes);
    for (const [id, box] of sub.boxes) {
      boxes.set(id, { id, x: box.x, y: box.y + y });
    }
    y += sub.height + TREE_GAP;
    maxW = Math.max(maxW, sub.width);
  }
  return { boxes, width: maxW, height: y };
}