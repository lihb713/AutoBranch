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
  /** ref 节点专属：展开/收缩被引文档预览。 */
  onToggleRef?: () => void;
  expanded?: boolean;
};

export function NodeCard({ node, selected, issueFields, onClick, onToggleRef, expanded }: NodeCardProps) {
  const name = node.name.trim() || node.type;
  const cls = [
    "node-card",
    selected ? "node-card--selected" : "",
    issueFields.size > 0 ? "node-card--issue" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const isRef = node.type === "ref";
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
      {isRef && onToggleRef ? (
        <button
          type="button"
          className="node-card__toggle"
          data-testid={`node-toggle-${node.id}`}
          onClick={(e) => {
            e.stopPropagation();
            onToggleRef();
          }}
        >
          {expanded ? "收缩" : "展开"}
        </button>
      ) : null}
    </div>
  );
}