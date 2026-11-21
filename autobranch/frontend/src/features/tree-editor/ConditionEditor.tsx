import { useMemo, useState } from "react";

import { Button } from "../../components/Button";
import { Combobox, type ComboboxOption } from "../../components/Combobox";
import { HighlightedField } from "../../components/HighlightedField";
import type { FunctionInfo } from "../../types/plugin";
import { schemaTypeToToken } from "./tokens";
import type { ConditionValue, PredicateExpr } from "./treeModel";

type ParamSpec = { type?: string; "x-autobranch-type"?: string; description?: string };
type ParamSchema = { properties?: Record<string, ParamSpec>; required?: string[] };

export function conditionSummary(value: ConditionValue | undefined): string {
  if (value === undefined) return "未设置";
  if (typeof value === "string") return value || "未设置";
  if (value.mode === "natural") return value.text || "未设置";
  return predicateSummary(value.expression);
}

export function predicateSummary(expr: PredicateExpr | undefined): string {
  if (!expr) return "空条件";
  if ("function" in expr) return expr.function || "未选函数";
  if ("not" in expr) return `NOT(${predicateSummary(expr.not)})`;
  const key = "all" in expr ? "all" : "any";
  const children = "all" in expr ? expr.all : expr.any;
  return `${key.toUpperCase()}(${children.map(predicateSummary).join(", ")})`;
}

export function isPredicateFunction(fn: FunctionInfo): boolean {
  const values = Object.values(fn.returns ?? {});
  return values.length === 1 && values[0] === "bool";
}

function expressionIssues(expr: PredicateExpr | undefined): string[] {
  if (!expr) return ["谓词条件不能为空"];
  if ("function" in expr) {
    return expr.function.trim() ? [] : ["谓词缺少函数名"];
  }
  if ("not" in expr) {
    return expressionIssues(expr.not);
  }
  const key = "all" in expr ? "all" : "any";
  const children = "all" in expr ? expr.all : expr.any;
  if (children.length === 0) return [`${key.toUpperCase()} 至少需要一个子条件`];
  return children.flatMap(expressionIssues);
}

type ConditionFieldProps = {
  label: string;
  value: ConditionValue | undefined;
  functions: FunctionInfo[];
  disabled?: boolean;
  onChange: (value: ConditionValue) => void;
  dataTestid?: string;
};

export function ConditionField({
  label,
  value,
  functions,
  disabled = false,
  onChange,
  dataTestid,
}: ConditionFieldProps) {
  const [open, setOpen] = useState(false);
  const mode = typeof value === "string" ? "natural" : value?.mode ?? "natural";
  const naturalText =
    typeof value === "string" ? value : value?.mode === "natural" ? value.text : "";
  const expression = value && typeof value !== "string" && value.mode === "predicate"
    ? value.expression
    : undefined;
  const hasContent = conditionSummary(value) !== "未设置";
  const predicateFunctions = useMemo(
    () => functions.filter(isPredicateFunction),
    [functions],
  );

  const switchMode = (next: "natural" | "predicate") => {
    if (next === mode) return;
    if (hasContent && !window.confirm("切换条件类型会清空当前内容，是否继续？")) return;
    onChange(
      next === "natural"
        ? { mode: "natural", text: "" }
        : { mode: "predicate", expression: { all: [] } },
    );
  };

  return (
    <div className="condition-field" data-testid={dataTestid}>
      <div className="condition-field__header">
        <span className="text-field__label">{label}</span>
        <div className="segmented" role="group" aria-label={`${label}类型`}>
          <button
            type="button"
            className={`segmented__button${mode === "natural" ? " segmented__button--active" : ""}`}
            disabled={disabled}
            data-testid={dataTestid ? `${dataTestid}-natural` : undefined}
            onClick={() => switchMode("natural")}
          >
            自然语言
          </button>
          <button
            type="button"
            className={`segmented__button${mode === "predicate" ? " segmented__button--active" : ""}`}
            disabled={disabled}
            data-testid={dataTestid ? `${dataTestid}-predicate` : undefined}
            onClick={() => switchMode("predicate")}
          >
            谓词表达式
          </button>
        </div>
      </div>

      {mode === "natural" ? (
        <>
          <HighlightedField
            label=""
            value={naturalText}
            placeholder="单行完整条件，如：出现“工作台”且金额大于 0"
            disabled={disabled}
            data-testid={dataTestid ? `${dataTestid}-text` : undefined}
            onChange={(e) => onChange({ mode: "natural", text: e.target.value })}
          />
          <p className="property-panel__hint">
            自然语言条件由 LLM 判断，不支持嵌套；需要组合时请使用谓词表达式。
          </p>
        </>
      ) : (
        <>
          <div className="condition-summary" data-testid={dataTestid ? `${dataTestid}-summary` : undefined}>
            {predicateSummary(expression)}
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled}
            data-testid={dataTestid ? `${dataTestid}-edit` : undefined}
            onClick={() => setOpen(true)}
          >
            编辑条件
          </Button>
        </>
      )}

      {open ? (
        <ConditionEditorModal
          initial={expression ?? { all: [] }}
          functions={predicateFunctions}
          onClose={() => setOpen(false)}
          onSave={(next) => {
            onChange({ mode: "predicate", expression: next });
            setOpen(false);
          }}
        />
      ) : null}
    </div>
  );
}

type ConditionEditorModalProps = {
  initial: PredicateExpr;
  functions: FunctionInfo[];
  onClose: () => void;
  onSave: (expression: PredicateExpr) => void;
};

function ConditionEditorModal({ initial, functions, onClose, onSave }: ConditionEditorModalProps) {
  const [expression, setExpression] = useState<PredicateExpr>(
    "function" in initial ? { all: [initial] } : initial,
  );
  const errors = expressionIssues(expression);

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div
        className="modal-panel condition-editor"
        data-testid="condition-editor"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="dialog-header">
          <span>编辑谓词表达式</span>
          <Button variant="ghost" size="sm" onClick={onClose}>
            关闭
          </Button>
        </div>
        <div className="condition-editor__body">
          <ExpressionNode
            expr={expression}
            functions={functions}
            onChange={setExpression}
            isRoot
          />
        </div>
        {errors.length > 0 ? (
          <ul className="condition-editor__errors" data-testid="condition-errors">
            {errors.map((error, i) => (
              <li key={i}>{error}</li>
            ))}
          </ul>
        ) : null}
        <div className="dialog-actions">
          <Button type="button" variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button
            type="button"
            disabled={errors.length > 0}
            data-testid="condition-save"
            onClick={() => onSave(expression)}
          >
            保存条件
          </Button>
        </div>
      </div>
    </div>
  );
}

type ExpressionNodeProps = {
  expr: PredicateExpr;
  functions: FunctionInfo[];
  onChange: (expr: PredicateExpr) => void;
  onDelete?: () => void;
  isRoot?: boolean;
};

function ExpressionNode({ expr, functions, onChange, onDelete, isRoot }: ExpressionNodeProps) {
  if ("function" in expr) {
    return (
      <PredicateLeafEditor
        expr={expr}
        functions={functions}
        onChange={onChange}
        onDelete={onDelete}
      />
    );
  }

  if ("not" in expr) {
    return (
      <div className="predicate-group predicate-group--not">
        <div className="predicate-group__header">
          <span className="predicate-group__title">NOT</span>
          {onDelete ? (
            <Button variant="ghost" size="sm" onClick={onDelete}>
              删除
            </Button>
          ) : null}
        </div>
        <ExpressionNode
          expr={expr.not}
          functions={functions}
          onChange={(next) => onChange({ not: next })}
        />
      </div>
    );
  }

  const key = "all" in expr ? "all" : "any";
  const children = "all" in expr ? expr.all : expr.any;
  const setChildren = (next: PredicateExpr[]) =>
    onChange(key === "all" ? { all: next } : { any: next });
  const add = (child: PredicateExpr) => setChildren([...children, child]);
  const replace = (index: number, child: PredicateExpr) =>
    setChildren(children.map((item, i) => (i === index ? child : item)));
  const remove = (index: number) => setChildren(children.filter((_, i) => i !== index));

  return (
    <div className="predicate-group">
      <div className="predicate-group__header">
        <span className="predicate-group__title">{key.toUpperCase()}</span>
        {onDelete && !isRoot ? (
          <Button variant="ghost" size="sm" onClick={onDelete}>
            删除
          </Button>
        ) : null}
      </div>
      {children.length === 0 ? (
        <p className="property-panel__hint">至少添加一个子条件。</p>
      ) : (
        children.map((child, index) => (
          <ExpressionNode
            key={index}
            expr={child}
            functions={functions}
            onChange={(next) => replace(index, next)}
            onDelete={() => remove(index)}
          />
        ))
      )}
      <div className="condition-editor__toolbar">
        <Button variant="ghost" size="sm" onClick={() => add(emptyPredicate())}>
          + 谓词
        </Button>
        <Button variant="ghost" size="sm" onClick={() => add({ all: [] })}>
          + ALL
        </Button>
        <Button variant="ghost" size="sm" onClick={() => add({ any: [] })}>
          + ANY
        </Button>
        <Button variant="ghost" size="sm" onClick={() => add({ not: emptyPredicate() })}>
          + NOT
        </Button>
      </div>
    </div>
  );
}

function emptyPredicate(): PredicateExpr {
  return { function: "", args: [], kwargs: {} };
}

function PredicateLeafEditor({
  expr,
  functions,
  onChange,
  onDelete,
}: {
  expr: Extract<PredicateExpr, { function: string }>;
  functions: FunctionInfo[];
  onChange: (expr: PredicateExpr) => void;
  onDelete?: () => void;
}) {
  const selected = functions.find((f) => f.full_name === expr.function);
  const schema = (selected?.parameters ?? {}) as ParamSchema;
  const properties = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  const params = Object.keys(properties);
  const options: ComboboxOption[] = functions.map((f) => ({
    value: f.full_name,
    label: f.full_name,
    description: f.description,
  }));

  const setFunction = (name: string) => {
    const fn = functions.find((f) => f.full_name === name);
    const fnSchema = (fn?.parameters ?? {}) as ParamSchema;
    const fnRequired = fnSchema.required ?? [];
    onChange({
      function: name,
      args: fnRequired.map(() => ""),
      kwargs: {},
    });
  };

  const paramValue = (name: string): string => {
    const index = params.indexOf(name);
    if (index >= 0 && index < expr.args.length) return expr.args[index] ?? "";
    const value = expr.kwargs?.[name];
    return value == null ? "" : String(value);
  };

  const setParam = (name: string, value: string) => {
    const index = params.indexOf(name);
    if (required.has(name)) {
      const args = [...expr.args];
      while (args.length <= index) args.push("");
      args[index] = value;
      onChange({ ...expr, args });
      return;
    }
    const kwargs = { ...(expr.kwargs ?? {}) };
    if (value === "") delete kwargs[name];
    else kwargs[name] = value;
    onChange({ ...expr, kwargs });
  };

  return (
    <div className="predicate-leaf">
      <div className="predicate-leaf__header">
        <span className="predicate-group__title">谓词</span>
        {onDelete ? (
          <Button variant="ghost" size="sm" onClick={onDelete}>
            删除
          </Button>
        ) : null}
      </div>
      <Combobox
        label="函数"
        value={expr.function}
        options={options}
        placeholder="选择单 bool 返回函数"
        dataTestid="predicate-function"
        onChange={setFunction}
      />
      {params.map((name) => {
        const spec = properties[name] ?? {};
        const token = schemaTypeToToken(spec.type, spec["x-autobranch-type"]);
        return (
          <HighlightedField
            key={name}
            label={`${required.has(name) ? "入参" : "可选参数"} ${name}（${token}）`}
            value={paramValue(name)}
            placeholder="变量名或字面量"
            data-testid={`predicate-arg-${name}`}
            onChange={(e) => setParam(name, e.target.value)}
          />
        );
      })}
    </div>
  );
}
