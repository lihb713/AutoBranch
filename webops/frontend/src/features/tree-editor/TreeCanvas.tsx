import { freeRoots, slotFields, type TreeDoc } from "./treeModel";
import { layoutDocument, NODE_H, NODE_W } from "./layout";
import { NodeCard } from "./NodeCard";

type TreeCanvasProps = {
  doc: TreeDoc;
  selectedId: string | null;
  issueByNode: Map<string, Set<string>>;
  refPreviews?: Record<string, TreeDoc>;
  onToggleRef?: (id: string) => void;
  onSelect: (id: string) => void;
};

type Edge = { x1: number; y1: number; x2: number; y2: number; key: string };

function edgePath(e: Edge): string {
  const midY = (e.y1 + e.y2) / 2;
  return `M ${e.x1} ${e.y1} L ${e.x1} ${midY} L ${e.x2} ${midY} L ${e.x2} ${e.y2}`;
}

/** 展开的 ref 预览：被引文档整棵只读子树（含内部连线，节点卡片只读）。 */
function PreviewSubtree({ preview, offsetX, offsetY }: { preview: TreeDoc; offsetX: number; offsetY: number }) {
  const free = freeRoots(preview);
  const layout = layoutDocument(preview.root, free, preview.nodes);
  return (
    <div className="canvas__preview" data-testid="ref-preview">
      {[...layout.boxes.entries()].map(([id, box]) => {
        const node = preview.nodes[id];
        if (!node) return null;
        return (
          <div
            key={id}
            className="canvas__node"
            data-testid={`preview-node-${id}`}
            style={{ left: offsetX + box.x, top: offsetY + box.y }}
          >
            <div className="node-card node-card--preview" data-node-type={node.type}>
              <span className="node-card__type">{node.type}</span>
              <span className="node-card__name">{node.name.trim() || node.type}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function TreeCanvas({
  doc,
  selectedId,
  issueByNode,
  refPreviews = {},
  onToggleRef,
  onSelect,
}: TreeCanvasProps) {
  const free = freeRoots(doc);
  const layout = layoutDocument(doc.root, free, doc.nodes);

  const edges: Edge[] = [];
  for (const node of Object.values(doc.nodes)) {
    const from = layout.boxes.get(node.id);
    if (!from) continue;
    for (const m of slotFields(node)) {
      if (!m.childId) continue;
      const to = layout.boxes.get(m.childId);
      if (!to) continue;
      edges.push({
        x1: from.x + NODE_W / 2,
        y1: from.y + NODE_H,
        x2: to.x + NODE_W / 2,
        y2: to.y,
        key: `${node.id}-${m.field}-${m.childId}`,
      });
    }
  }

  // 展开的 ref 预览：内部连线 + ref → 预览根 连接主树
  const previewOffsets: { refId: string; offsetX: number; offsetY: number }[] = [];
  for (const [refId, preview] of Object.entries(refPreviews)) {
    const refBox = layout.boxes.get(refId);
    if (!refBox) continue;
    const pl = layoutDocument(preview.root, freeRoots(preview), preview.nodes);
    const offX = refBox.x;
    const offY = refBox.y + NODE_H + 24;
    previewOffsets.push({ refId, offsetX: offX, offsetY: offY });
    // ref → 预览根 连接线
    const rootBox = pl.boxes.get(preview.root);
    if (rootBox) {
      edges.push({
        x1: refBox.x + NODE_W / 2,
        y1: refBox.y + NODE_H,
        x2: offX + rootBox.x + NODE_W / 2,
        y2: offY + rootBox.y,
        key: `${refId}-ref-root`,
      });
    }
    // 预览内部父子连线
    for (const node of Object.values(preview.nodes)) {
      const from = pl.boxes.get(node.id);
      if (!from) continue;
      for (const m of slotFields(node)) {
        if (!m.childId) continue;
        const to = pl.boxes.get(m.childId);
        if (!to) continue;
        edges.push({
          x1: offX + from.x + NODE_W / 2,
          y1: offY + from.y + NODE_H,
          x2: offX + to.x + NODE_W / 2,
          y2: offY + to.y,
          key: `${refId}-${node.id}-${m.childId}`,
        });
      }
    }
  }

  const hasRoot = doc.root in doc.nodes && Object.keys(doc.nodes).length > 0;

  return (
    <main className="canvas" data-testid="tree-canvas">
      {hasRoot ? (
        <div
          className="canvas__scroll"
          style={{ width: layout.width + 320, height: layout.height + 320 }}
        >
          <svg
            className="canvas__edges"
            width={layout.width + 320}
            height={layout.height + 320}
            data-testid="canvas-edges"
          >
            {edges.map((e) => (
              <path
                key={e.key}
                d={edgePath(e)}
                fill="none"
                stroke="#94a3b8"
                strokeWidth={1.5}
                data-testid="tree-edge"
              />
            ))}
          </svg>
          {[...layout.boxes.entries()].map(([id, box]) => {
            const node = doc.nodes[id];
            if (!node) return null;
            return (
              <div key={id} className="canvas__node" style={{ left: box.x, top: box.y }}>
                <NodeCard
                  node={node}
                  selected={selectedId === id}
                  issueFields={issueByNode.get(id) ?? new Set()}
                  onClick={onSelect}
                  onToggleRef={
                    node.type === "ref" && onToggleRef ? () => onToggleRef(id) : undefined
                  }
                  expanded={node.type === "ref" && refPreviews[id] !== undefined}
                />
              </div>
            );
          })}
          {previewOffsets.map(({ refId, offsetX, offsetY }) => (
            <PreviewSubtree
              key={`preview-${refId}`}
              preview={refPreviews[refId]}
              offsetX={offsetX}
              offsetY={offsetY}
            />
          ))}
          {free.map((fid) => {
            const box = layout.boxes.get(fid);
            if (!box) return null;
            return (
              <div
                key={`free-label-${fid}`}
                className="canvas__free-label"
                data-testid={`free-tree-label-${fid}`}
                style={{ left: box.x, top: box.y - 24 }}
              >
                {doc.nodes[fid]?.name || fid} · 游离
              </div>
            );
          })}
        </div>
      ) : (
        <div className="canvas__empty" data-testid="canvas-empty">
          <p>画布为空</p>
          <p className="canvas__drop-hint">从左侧节点面板添加节点构建行为树</p>
        </div>
      )}
    </main>
  );
}