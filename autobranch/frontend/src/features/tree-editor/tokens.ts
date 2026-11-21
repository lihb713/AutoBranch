/** 行为树编辑器共享类型词表与 JSON Schema 类型映射。 */

/** 前端类型 token（文档 inputs/outputs、ref/FunctionCall 返回类型下拉）。 */
export const TYPE_TOKENS = [
  "str",
  "int",
  "float",
  "bool",
  "array",
  "object",
  "generics",
  "page_ref",
] as const;

/** 后端函数参数 JSON Schema 类型 → 前端类型 token。 */
export function schemaTypeToToken(
  t: string | undefined,
  customType?: string,
): string {
  if (customType) return customType;
  switch (t) {
    case "string":
      return "str";
    case "integer":
      return "int";
    case "number":
      return "float";
    case "boolean":
      return "bool";
    case "page_ref":
      return "page_ref";
    case "array":
      return "array";
    case "object":
      return "object";
    default:
      return "generics";
  }
}