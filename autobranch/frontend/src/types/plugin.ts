export interface PluginOut {
  id: number;
  name: string;
  kind: "builtin" | "custom";
  description: string;
  functions: string[];
  created_at: string;
  updated_at: string;
}

export interface PluginDetailOut extends PluginOut {
  source: string | null;
}

export interface PluginCreate {
  name: string;
  source: string;
}

export interface PluginUpdate {
  source: string;
}

export interface PluginCheckError {
  line: number | null;
  column: number | null;
  type: string;
  message: string;
  constraint: string;
}

export interface PluginCheckOut {
  ok: boolean;
  errors: PluginCheckError[];
}

export interface PluginDeleteOut {
  affected_trees: string[];
}

export interface FunctionInfo {
  full_name: string;
  plugin: string;
  name: string;
  description: string;
  returns: string[];
  parameters: Record<string, unknown>;
}