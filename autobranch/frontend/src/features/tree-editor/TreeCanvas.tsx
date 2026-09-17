import { useRef, useState } from "react";
import { freeRoots, slotFields, type TreeDoc } from "./treeModel";
import { layoutDocument, prefixTree, NODE_H, NODE_W } from "./layout";
import { NodeCard } from "./NodeCard";

type TreeCanvasProps = {
  doc: TreeDoc;
  selectedId: string | null;
  issueByNode: Map<string, Set<string>>;
  refPreviews?: Record<string, TreeDoc>;
  onToggleRef?: (id: string) => void;
  onSelect: (id: string) => void;
  /** 点击展开预览中的节点（查看只读属性）。 */
  onSelectPreview?: (refId: string, nodeId: string) => void;
};

type Edge = { x1: number; y1: number; x2: number; y2: number; key: string };

function edgePath(e: Edge): string {
  const midY = (e.y1 + e.y2) / 2;
  return `M ${e.x1} ${e.y1} L ${e.x1} ${midY} L ${e.x2} ${midY} L ${e.x2} ${e.y2}`;
}

export function TreeCanvas({
  doc,
  selectedId,
  issueByNode,
  refPreviews = {},
  onToggleRef,
  onSelect,
  onSelectPreview,
}: TreeCanvasProps) {
  const [zoom, setZoom] = useState(1);
  const canvasRef = useRef<HTMLElement | null>(null);
  const free = freeRoots(doc);
  // 预览子树并入主树布局（ref → 预览根 视作子节点，向下生长避免重叠）
  const layout = layoutDocument(doc.root, free, doc.nodes, refPreviews);

  // 全部节点表（主树 + 预览前缀节点，用于画边与渲染预览）
  const allNodes: Record<string, TreeDoc["nodes"][string]> = { ...doc.nodes };
  const previewSource: Record<string, { refId: string; nodeId: string }> = {};
  for (const [refId, preview] of Object.entries(refPreviews)) {
    const prefix = `${refId}:`;
    Object.assign(allNodes, prefixTree(preview, prefix));
    for (const nodeId of Object.keys(preview.nodes)) {
      previewSource[`${prefix}${nodeId}`] = { refId, nodeId };
    }
  }

  // 收集连线：主树内部 + 预览内部 + ref → 预览根
  const edges: Edge[] = [];
  for (const node of Object.values(allNodes)) {
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
  for (const refId of Object.keys(refPreviews)) {
    const refBox = layout.boxes.get(refId);
    const rootKey = `${refId}:${refPreviews[refId].root}`;
    const rootBox = layout.boxes.get(rootKey);
    if (refBox && rootBox) {
      edges.push({
        x1: refBox.x + NODE_W / 2,
        y1: refBox.y + NODE_H,
        x2: rootBox.x + NODE_W / 2,
        y2: rootBox.y,
        key: `${refId}-ref-root`,
      });
    }
  }

  const hasRoot = doc.root in doc.nodes && Object.keys(doc.nodes).length > 0;

  const zoomIn = () => setZoom((z) => Math.min(3, +Math.min(3, z + 0.1).toFixed(2)));
  const zoomOut = () => setZoom((z) => Math.max(0.25, +(z - 0.1).toFixed(2)));
  const zoomReset = () => setZoom(1);
  const zoomFit = () => {
    const el = canvasRef.current;
    if (!el) return;
    const contentW = layout.width + 40;
    const contentH = layout.height + 40;
    const fit = Math.min(el.clientWidth / contentW, el.clientHeight / contentH, 1);
    setZoom(Math.max(0.25, +fit.toFixed(2)));
  };

  const contentW = layout.width + 40;
  const contentH = layout.height + 40;

  return (
    <main className="canvas" data-testid="tree-canvas" ref={canvasRef}>
      {hasRoot ? (
        <>
          <div
            className="canvas__scroll"
            style={{ width: contentW * zoom, height: contentH * zoom }}
          >
            <div
              className="canvas__zoom"
              style={{ transform: `scale(${zoom})`, transformOrigin: "0 0" }}
            >
              <svg
                className="canvas__edges"
                width={contentW}
                height={contentH}
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
            const node = allNodes[id];
            if (!node) return null;
            const isPreview = previewSource[id] !== undefined;
            if (isPreview) {
              const { refId, nodeId } = previewSource[id];
              return (
                <div key={id} className="canvas__node" style={{ left: box.x, top: box.y }}>
                  <div
                    className="node-card node-card--preview"
                    data-testid={`preview-node-${nodeId}`}
                    data-node-type={node.type}
                    onClick={() => onSelectPreview?.(refId, nodeId)}
                  >
                    <span className="node-card__type">{node.type}</span>
                    <span className="node-card__name">{node.name.trim() || node.type}</span>
                  </div>
                </div>
              );
            }
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
          </div>
          <div className="canvas__zoombar" data-testid="canvas-zoombar">
            <button
              type="button"
              className="canvas__zoom-btn"
              onClick={zoomOut}
              data-testid="zoom-out"
              aria-label="缩小"
            >
              −
            </button>
            <span className="canvas__zoom-level" data-testid="zoom-level">
              {Math.round(zoom * 100)}%
            </span>
            <button
              type="button"
              className="canvas__zoom-btn"
              onClick={zoomIn}
              data-testid="zoom-in"
              aria-label="放大"
            >
              ＋
            </button>
            <button
              type="button"
              className="canvas__zoom-btn"
              onClick={zoomFit}
              data-testid="zoom-fit"
            >
              适应
            </button>
            <button
              type="button"
              className="canvas__zoom-btn"
              onClick={zoomReset}
              data-testid="zoom-reset"
            >
              100%
            </button>
          </div>
        </>
      ) : (
        <div className="canvas__empty" data-testid="canvas-empty">
          <p>画布为空</p>
          <p className="canvas__drop-hint">从「节点」面板添加节点构建行为树</p>
        </div>
      )}
    </main>
  );
}