export type TreeStatus = "draft" | "published";

export type TreeOut = {
  id: number;
  name: string;
  status: TreeStatus;
  created_at: string;
  updated_at: string;
  inputs: Record<string, string>;
};

export type TreeDetailOut = TreeOut & {
  content: string;
};

export type TreeCreate = {
  name: string;
  content: string;
};

export type TreeUpdate = {
  name?: string;
  content?: string;
};

export type TreeCommand = {
  op:
    | "add_node"
    | "delete_node"
    | "update_node"
    | "update_doc"
    | "set_slot"
    | "detach_slot";
  node_type?: string;
  node_id?: string;
  subtree?: boolean;
  patch?: Record<string, unknown>;
  slot_index?: number;
  child_id?: string | null;
};

export type TreeCommandsOut = {
  tree: TreeDetailOut;
  created_node_id: string | null;
};
