import type { DragEvent } from "react";
import { Button } from "../../components/Button";
import { TextField } from "../../components/TextField";
import type { EditorNode, EditorNodeType } from "../../types/node";
import { NODE_FIELD_DEFS, fieldValue } from "./model";

const DRAG_TYPE = "text/webops-node-type";
const DRAG_ID = "text/webops-node-id";

type CanvasTreeProps = {
  root: EditorNode | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onSetField: (id: string, key: string, value: string) => void;
  onSetFields: (id: string, fields: { key: string; value: string }[]) => void;
  onRemove: (id: string) => void;
  onMove: (id: string, targetParentId: string | null) => void;
  onDropNode: (parentId: string | null, nodeType: EditorNodeType) => void;
  onAddChild: (parentId: string) => void;
};

function allowDrop(e: DragEvent) {
  e.preventDefault();
  e.dataTransfer.dropEffect = "copy";
}

function BranchRowEditor({
  node,
  onSetFields,
  onRemove,
}: {
  node: EditorNode;
  onSetFields: (id: string, fields: { key: string; value: string }[]) => void;
  onRemove: (id: string) => void;
}) {
  const isOtherwise = node.fields.some((f) => f.key === "otherwise");
  const target = fieldValue(node, isOtherwise ? "otherwise" : "then");

  return (
    <div className="tree-node tree-node--branch" data-testid={`node-${node.id}`}>
      <div className="tree-node__header">
        <span className="tree-node__type">分支</span>
        <Button
          variant="danger"
          onClick={(e) => {
            e.stopPropagation();
            onRemove(node.id);
          }}
        >
          移除
        </Button>
      </div>
      <div className="tree-node__fields">
        <label className="text-field">
          <span className="text-field__label">分支类型</span>
          <select
            className="text-field__input"
            value={isOtherwise ? "otherwise" : "when"}
            onChange={(e) => {
              if (e.target.value === "otherwise") {
                onSetFields(node.id, [{ key: "otherwise", value: fieldValue(node, "then") }]);
              } else {
                onSetFields(node.id, [
                  { key: "when", value: "" },
                  { key: "then", value: fieldValue(node, "otherwise") },
                ]);
              }
            }}
          >
            <option value="when">when（条件）</option>
            <option value="otherwise">otherwise（兜底）</option>
          </select>
        </label>
        {!isOtherwise ? (
          <TextField
            label="条件 when"
            placeholder='如：出现"工作台"'
            value={fieldValue(node, "when")}
            onChange={(e) => onSetFields(node.id, [{ key: "when", value: e.target.value }])}
          />
        ) : null}
        <TextField
          label="目标 then"
          placeholder="如：导出报表"
          value={target}
          onChange={(e) =>
            onSetFields(
              node.id,
              isOtherwise
                ? [{ key: "otherwise", value: e.target.value }]
                : [
                    { key: "when", value: fieldValue(node, "when") },
                    { key: "then", value: e.target.value },
                  ],
            )
          }
        />
      </div>
    </div>
  );
}

function TreeNodeView({
  node,
  depth,
  selectedId,
  onSelect,
  onSetField,
  onSetFields,
  onRemove,
  onMove,
  onDropNode,
  onAddChild,
}: CanvasTreeProps & { node: EditorNode; depth: number }) {
  const canHaveChildren = node.type === "Sequence" || node.type === "Branch" || node.type === "Retry";
  const isBranchRow = node.type === "branch";

  return (
    <div
      className={`tree-node${selectedId === node.id ? " tree-node--selected" : ""}`}
      data-testid={`node-${node.id}`}
      data-node-type={node.type}
      draggable
      onClick={() => onSelect(node.id)}
      onDragStart={(e) => {
        e.stopPropagation();
        e.dataTransfer.setData(DRAG_ID, node.id);
        e.dataTransfer.effectAllowed = "move";
      }}
      onDragOver={(e) => {
        e.stopPropagation();
        if (canHaveChildren) allowDrop(e);
      }}
      onDrop={(e) => {
        e.stopPropagation();
        e.preventDefault();
        const nodeType = e.dataTransfer.getData(DRAG_TYPE);
        const draggedId = e.dataTransfer.getData(DRAG_ID);
        if (nodeType) {
          onDropNode(node.id, nodeType as EditorNodeType);
        } else if (draggedId) {
          onMove(draggedId, node.id);
        }
      }}
    >
      {!isBranchRow ? (
        <>
          <div className="tree-node__header">
            <span className="tree-node__type">{node.type}</span>
            <div className="page-actions">
              <Button
                variant="ghost"
                onClick={(e) => {
                  e.stopPropagation();
                  onMove(node.id, null);
                }}
              >
                移至根
              </Button>
              <Button
                variant="danger"
                onClick={(e) => {
                  e.stopPropagation();
                  onRemove(node.id);
                }}
              >
                移除
              </Button>
            </div>
          </div>
          {NODE_FIELD_DEFS[node.type].length > 0 ? (
            <div className="tree-node__fields">
              {NODE_FIELD_DEFS[node.type].map((def) => (
                <TextField
                  key={def.key}
                  label={def.label}
                  placeholder={def.placeholder}
                  value={fieldValue(node, def.key)}
                  onChange={(e) => onSetField(node.id, def.key, e.target.value)}
                />
              ))}
            </div>
          ) : null}
        </>
      ) : (
        <BranchRowEditor node={node} onSetFields={onSetFields} onRemove={onRemove} />
      )}
      {canHaveChildren ? (
        <div className="tree-node__children" data-testid={`children-${node.id}`}>
          {node.children.map((child) => (
            <TreeNodeView
              key={child.id}
              node={child}
              depth={depth + 1}
              root={null}
              selectedId={selectedId}
              onSelect={onSelect}
              onSetField={onSetField}
              onSetFields={onSetFields}
              onRemove={onRemove}
              onMove={onMove}
              onDropNode={onDropNode}
              onAddChild={onAddChild}
            />
          ))}
          <button
            type="button"
            className="tree-node__add"
            onClick={(e) => {
              e.stopPropagation();
              onAddChild(node.id);
            }}
          >
            {node.type === "Branch" ? "+ 添加分支" : "+ 添加子节点"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function CanvasTree({
  root,
  selectedId,
  onSelect,
  onSetField,
  onSetFields,
  onRemove,
  onMove,
  onDropNode,
  onAddChild,
}: CanvasTreeProps) {
  return (
    <main className="canvas">
      {root === null ? (
        <div
          className="canvas__empty"
          data-testid="canvas-drop-root"
          onDragOver={allowDrop}
          onDrop={(e) => {
            e.preventDefault();
            const nodeType = e.dataTransfer.getData(DRAG_TYPE);
            const draggedId = e.dataTransfer.getData(DRAG_ID);
            if (nodeType) {
              onDropNode(null, nodeType as EditorNodeType);
            } else if (draggedId) {
              onMove(draggedId, null);
            }
          }}
        >
          <p>画布为空</p>
          <p className="canvas__drop-hint">从左侧面板拖拽节点到这里开始构建行为树</p>
        </div>
      ) : (
        <TreeNodeView
          node={root}
          depth={0}
          root={root}
          selectedId={selectedId}
          onSelect={onSelect}
          onSetField={onSetField}
          onSetFields={onSetFields}
          onRemove={onRemove}
          onMove={onMove}
          onDropNode={onDropNode}
          onAddChild={onAddChild}
        />
      )}
    </main>
  );
}