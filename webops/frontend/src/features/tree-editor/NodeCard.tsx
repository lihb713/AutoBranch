import type { TreeNode } from "./treeModel";

export const TYPE_COLORS: Record<string, string> = {
  Root: "#334155",
  Sequence: "#2563eb",
  Step: "#16a34a",
  IfThenElse: "#7c3aed",
  Branch: "#ea580c",
  Retry: "#dc2626",
  LoopUntil: "#0d9488",
  Action: "#64748b",
  ref: "#0891b2",
};

type NodeCardProps = {
  node: TreeNode;
  selected: boolean;
  issueFields: Set<string>;
  onClick: (id: string) => void;
  onDelete: (id: string, subtree: boolean) => void;
};

export function NodeCard({ node, selected, issueFields, onClick, onDelete }: NodeCardProps) {
  const name = node.name.trim() || node.type;
  const isRoot = node.type === "Root";
  const cls = [
    "node-card",
    selected ? "node-card--selected" : "",
    issueFields.size > 0 ? "node-card--issue" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div
      className={cls}
      data-testid={`node-card-${node.id}`}
      data-node-type={node.type}
      onClick={() => onClick(node.id)}
      style={{ borderColor: TYPE_COLORS[node.type] ?? "#64748b" }}
    >
      <span className="node-card__type" data-testid={`node-type-${node.id}`}>
        {node.type}
      </span>
      <span className="node-card__name" data-testid={`node-name-${node.id}`}>
        {name}
      </span>
      <span className="node-card__actions">
        <button
          type="button"
          data-testid={`node-delete-${node.id}`}
          disabled={isRoot}
          onClick={(e) => {
            e.stopPropagation();
            onDelete(node.id, false);
          }}
          title="删除单节点（子节点各自成游离树）"
        >
          删
        </button>
        <button
          type="button"
          data-testid={`node-delete-subtree-${node.id}`}
          disabled={isRoot}
          onClick={(e) => {
            e.stopPropagation();
            onDelete(node.id, true);
          }}
          title="删除子树（连带后代）"
        >
          子树
        </button>
      </span>
    </div>
  );
}