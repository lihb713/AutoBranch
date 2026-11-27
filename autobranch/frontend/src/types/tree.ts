export type TreeStatus = "draft" | "published";

export type TreeGroup = {
  id: number;
  name: string;
  is_default: boolean;
  tree_count: number;
};

export type TreeOut = {
  id: number;
  name: string;
  status: TreeStatus;
  description?: string;
  group_id?: number | null;
  group_name?: string;
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
  description?: string;
  group_id?: number;
};

export type TreeUpdate = {
  name?: string;
  content?: string;
  description?: string;
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
