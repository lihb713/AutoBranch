export interface PluginPage {
  route: string;
  label: string;
  component: string;
  icon?: string;
}

export interface PluginManifest {
  pages: PluginPage[];
}

export interface ConfigSchemaItem {
  key: string;
  label: string;
  type: "string" | "number" | "boolean";
  default?: string | number | boolean;
  required?: boolean;
  description?: string;
}

export interface PluginCustomType {
  token: string;
  class_name: string;
  description: string;
  constructible: boolean;
}

export interface PluginOut {
  id: number;
  name: string;
  kind: "builtin" | "custom";
  description: string;
  functions: string[];
  custom_types?: PluginCustomType[];
  frontend_manifest?: PluginManifest | null;
  config_schema?: ConfigSchemaItem[] | null;
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

export interface PluginManifestOut {
  frontend_manifest: PluginManifest | null;
  config_schema: ConfigSchemaItem[] | null;
  custom_types: PluginCustomType[];
}

export interface FunctionInfo {
  full_name: string;
  plugin: string;
  name: string;
  description: string;
  returns: Record<string, string>;
  parameters: Record<string, unknown>;
  output_param?: string | null;
  user_visible?: boolean;
}
