import { slotFields, type TreeDoc } from "./treeModel";

/** 前端即时校验问题（用于红框定位与保存汇总展示）。 */
export type ClientIssue = {
  code: string;
  message: string;
  nodeId?: string;
  field?: string;
};

/** 被引文档的接口声明（经 by-name API 加载）。 */
export type RefMeta = {
  inputs: Record<string, string>;
  outputs: string[];
};

export type ValidateContext = {
  /** 系统内已存在的文档名（含当前文档名）。 */
  docNames: string[];
  /** 已加载的被引文档声明（target → meta）。 */
  refMeta: Record<string, RefMeta>;
  /** 文档引用图：文档名 → 其内 ref 目标文档名列表（跨文档环检测用）。 */
  refTargetsOf: (name: string) => string[];
};

/** 各类型必填槽位字段（引用子树根，空槽位报错）。 */
export const REQUIRED_SLOT_FIELDS: Record<string, string[]> = {
  Step: ["action"],
  IfThenElse: ["then", "else"],
  Retry: ["body"],
  LoopUntil: ["action"],
  Branch: ["action"],
  Root: ["body"],
  Sequence: [],
  Action: [],
  ref: [],
  FunctionCall: [],
};

/** 各类型必填标量字段（fields 中）。 */
export const REQUIRED_SCALAR_FIELDS: Record<string, string[]> = {
  Action: ["description"],
  Step: ["expect"],
  IfThenElse: ["if"],
  LoopUntil: ["until", "max"],
  Retry: ["max"],
  Branch: [],
  Root: [],
  Sequence: [],
  ref: [],
  FunctionCall: [],
};

const LITERAL_TOKENS = ["str", "int", "float", "bool"];

function literalMatches(typ: string, value: string): boolean {
  if (typ === "str") return true;
  if (typ === "int") return /^[+-]?\d+$/.test(value);
  if (typ === "float") return /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(value);
  if (typ === "bool") return value === "true" || value === "false";
  return true;
}

const SET_TMPL = /\[\[\s*set:(?:(str|int|float|bool|page_ref|object):)?\s*(?:this\/)?([^[\]:]+?)\s*\]\]/g;

function bareName(path: string): string {
  return path.replace(/^(?:this\/|\$this\/)/, "");
}

/** 收集本树已声明变量：文档级 inputs + 各叶子 [[set:...]] 目标 + 各 ref returns 键。 */
export function collectDeclaredVars(doc: TreeDoc): Set<string> {
  const vars = new Set<string>(Object.keys(doc.inputs));
  for (const node of Object.values(doc.nodes)) {
    if (node.type === "ref" || node.type === "FunctionCall") {
      for (const key of Object.keys(node.returns ?? {})) vars.add(key);
    } else {
      for (const desc of Object.values(node.fields)) {
        for (const m of desc.matchAll(SET_TMPL)) vars.add(bareName(m[2]));
      }
    }
  }
  return vars;
}

/** args 元素是否为本树变量引用（`this/<名>` 或裸名命中已声明变量）。 */
export function exprIsVariable(doc: TreeDoc, expr: string): boolean {
  const parts = expr.trim().split("/").filter((p) => p);
  if (parts.length === 2 && parts[0] === "this") return collectDeclaredVars(doc).has(parts[1]);
  if (parts.length === 1) return collectDeclaredVars(doc).has(parts[0]);
  return false;
}

/** 子树中是否存在引用环（DFS 灰白黑）。 */
export function hasCycle(
  start: string,
  doc: TreeDoc,
  childOf: (id: string) => string[],
): boolean {
  const gray = new Set<string>();
  const black = new Set<string>();
  const visit = (id: string): boolean => {
    if (black.has(id)) return false;
    if (gray.has(id)) return true;
    gray.add(id);
    for (const c of childOf(id)) {
      if (c in doc.nodes && visit(c)) return true;
    }
    gray.delete(id);
    black.add(id);
    return false;
  };
  return visit(start);
}

/** 主树与各游离树无环（孤儿引用已在前序校验报错）。 */
export function checkAcyclic(doc: TreeDoc): ClientIssue[] {
  const issues: ClientIssue[] = [];
  const childOf = (id: string) =>
    (doc.nodes[id] ? slotFields(doc.nodes[id]) : [])
      .map((m) => m.childId)
      .filter((c): c is string => c !== null);
  const referenced = new Set<string>();
  for (const n of Object.values(doc.nodes)) {
    for (const m of slotFields(n)) {
      if (m.childId) referenced.add(m.childId);
    }
  }
  const starts = [doc.root, ...Object.keys(doc.nodes).filter((id) => !referenced.has(id))];
  for (const s of starts) {
    if (s in doc.nodes && hasCycle(s, doc, childOf)) {
      issues.push({ code: "cycle", message: `槽位引用存在循环（起点 '${s}'）`, nodeId: s });
    }
  }
  return issues;
}

/** 选目标文档是否形成跨文档引用环（target → … → 本文档）。 */
export function wouldCreateCycle(
  target: string,
  docName: string,
  refTargetsOf: (name: string) => string[],
): boolean {
  const queue = [target];
  const seen = new Set<string>([target]);
  while (queue.length > 0) {
    const cur = queue.shift()!;
    if (cur === docName) return true;
    for (const t of refTargetsOf(cur)) {
      if (!seen.has(t)) {
        seen.add(t);
        queue.push(t);
      }
    }
  }
  return false;
}

/** 即时校验：单根 / 孤儿槽位 / 重复引用 / 必填（槽位+标量） / Branch 分支 / ref 目标与参数 / 无环 / 跨文档环。 */
export function validateDoc(doc: TreeDoc, ctx: ValidateContext): ClientIssue[] {
  const issues: ClientIssue[] = [];

  // 单根
  const roots = Object.values(doc.nodes).filter((n) => n.type === "Root");
  if (roots.length !== 1) {
    issues.push({ code: "single_root", message: `文档应恰有一个 type:Root 节点（当前 ${roots.length} 个）` });
  } else if (!(doc.root in doc.nodes) || doc.nodes[doc.root].type !== "Root") {
    issues.push({ code: "bad_root", message: `root 引用 '${doc.root}' 必须指向 type:Root 节点` });
  }

  // 槽位引用：孤儿 / 重复引用
  const referenced = new Set<string>();
  for (const n of Object.values(doc.nodes)) {
    for (const m of slotFields(n)) {
      const cid = m.childId;
      if (!cid) continue;
      if (!(cid in doc.nodes)) {
        issues.push({ code: "orphan_slot", message: `节点「${n.name}」槽位引用不存在的节点 '${cid}'`, nodeId: n.id });
      } else if (referenced.has(cid)) {
        issues.push({ code: "duplicate_reference", message: `节点 '${cid}' 被多个槽位引用，破坏纯树结构`, nodeId: cid });
      }
      referenced.add(cid);
    }
  }

  // 必填（槽位 + 标量）+ Branch 分支 + ref
  for (const n of Object.values(doc.nodes)) {
    const mounts = slotFields(n);
    for (const field of REQUIRED_SLOT_FIELDS[n.type] ?? []) {
      const has = mounts.some((m) => m.field === field && m.childId);
      if (!has) {
        issues.push({ code: "missing_slot", message: `节点「${n.name}」缺少必需槽位 ${field}`, nodeId: n.id, field });
      }
    }
    for (const f of REQUIRED_SCALAR_FIELDS[n.type] ?? []) {
      if (!(n.fields[f] ?? "").trim()) {
        issues.push({ code: "missing_field", message: `节点「${n.name}」缺少必填字段 ${f}`, nodeId: n.id, field: f });
      }
    }
    if (n.type === "Branch") {
      const branches = n.branches ?? [];
      if (branches.length === 0) {
        issues.push({ code: "missing_branches", message: "Branch 缺少分支（至少一个 when 或 otherwise）", nodeId: n.id });
      } else {
        branches.forEach((b, i) => {
          if (!(b.when ?? "").trim() && !(b.otherwise ?? "").trim()) {
            issues.push({ code: "bad_branch", message: `分支 ${i + 1} 缺少 when 或 otherwise`, nodeId: n.id });
          }
        });
      }
    }
    if (n.type === "ref") {
      const target = (n.target ?? "").trim();
      if (!target) {
        issues.push({ code: "missing_target", message: "ref 缺少目标文档", nodeId: n.id });
        continue;
      }
      if (!ctx.docNames.includes(target)) {
        issues.push({ code: "missing_doc", message: `引用文档「${target}」不存在`, nodeId: n.id });
      }
      if (wouldCreateCycle(target, doc.tree, ctx.refTargetsOf)) {
        issues.push({ code: "cross_doc_cycle", message: `引用「${target}」形成跨文档循环`, nodeId: n.id });
      }
      const meta = ctx.refMeta[target];
      if (meta) {
        const argCount = (n.args ?? []).length;
        const inputNames = Object.keys(meta.inputs);
        if (argCount !== inputNames.length) {
          issues.push({ code: "args_mismatch", message: `args 数量 ${argCount} ≠ 入参 ${inputNames.length}`, nodeId: n.id });
        }
        const retCount = Object.keys(n.returns ?? {}).length;
        if (retCount !== meta.outputs.length) {
          issues.push({ code: "returns_mismatch", message: `returns 数量 ${retCount} ≠ 出参 ${meta.outputs.length}`, nodeId: n.id });
        }
        for (const key of Object.keys(n.returns ?? {})) {
          if (key in doc.inputs) {
            issues.push({ code: "name_conflict", message: `接收参数「${key}」与本树入参重名`, nodeId: n.id });
          }
        }
        (n.args ?? []).forEach((expr, i) => {
          const typ = meta.inputs[inputNames[i]];
          if (!typ || typ === "page_ref" || !LITERAL_TOKENS.includes(typ)) return;
          if (exprIsVariable(doc, expr)) return;
          if (!literalMatches(typ, expr)) {
            issues.push({ code: "type_mismatch", message: `实参「${expr}」不是 ${typ} 字面量`, nodeId: n.id });
          }
        });
      }
    }
    if (n.type === "FunctionCall") {
      if (!(n.function ?? "").trim()) {
        issues.push({
          code: "missing_function",
          message: `节点「${n.name}」缺少函数名（function）`,
          nodeId: n.id,
        });
      }
    }
  }

  issues.push(...checkAcyclic(doc));
  return issues;
}