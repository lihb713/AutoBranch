export type CompositeNodeType =
  | "Step"
  | "Branch"
  | "LoopUntil"
  | "IfThenElse"
  | "Retry"
  | "Sequence"
  | "ref";

export type EditorNodeType = CompositeNodeType | "branch";

export type EditorField = {
  key: string;
  value: string;
};

export type EditorNode = {
  id: string;
  type: EditorNodeType;
  fields: EditorField[];
  children: EditorNode[];
};