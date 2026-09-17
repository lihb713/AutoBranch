import { useEffect, useState } from "react";
import { pluginsApi } from "../../api/plugins";
import { Combobox, type ComboboxOption } from "../../components/Combobox";
import { TextField } from "../../components/TextField";
import type { FunctionInfo } from "../../types/plugin";
import { DocInterfaceEditor } from "./DocInterfaceEditor";
import {
  detachSlot,
  freeRoots,
  setSlot,
  slotFields,
  type BranchRow,
  type TreeDoc,
  type TreeNode,
} from "./treeModel";
import { wouldCreateCycle, type RefMeta } from "./validation";

const SCALAR_FIELDS: Record<string, { key: string; label: string; placeholder?: string }[]> = {
  Action: [{ key: "description", label: "操作描述", placeholder: "如：点击\"登录\"" }],
  Step: [{ key: "expect", label: "验证 expect", placeholder: "如：出现\"工作台\"" }],
  IfThenElse: [{ key: "if", label: "判断 if", placeholder: "如：存在\"下载成功\"" }],
  LoopUntil: [
    { key: "until", label: "终止条件 until", placeholder: "如：出现\"最后一页\"" },
    { key: "max", label: "循环上限 max", placeholder: "如：50" },
  ],
  Retry: [{ key: "max", label: "重试上限 max", placeholder: "如：3" }],
  Root: [],
  Sequence: [],
  Branch: [],
  ref: [],
};

const TYPE_TOKENS = ["str", "int", "float", "bool", "page_ref", "object"];

type PropertyPanelProps = {
  doc: TreeDoc;
  node: TreeNode | null;
  /** 只读模式（ref 展开预览节点）：展示节点信息，禁止编辑。 */
  readonly?: boolean;
  docNames: string[];
  refMeta: Record<string, RefMeta>;
  refTargetsOf: (name: string) => string[];
  onUpdate: (doc: TreeDoc) => void;
  onLoadRefMeta: (target: string) => void;
  onDeleteNode: (id: string, subtree: boolean) => void;
};

function nodeLabel(doc: TreeDoc, id: string): string {
  const n = doc.nodes[id];
  return n ? n.name.trim() || n.type : id;
}

export function PropertyPanel({
  doc,
  node,
  readonly = false,
  docNames,
  refMeta,
  refTargetsOf,
  onUpdate,
  onLoadRefMeta,
  onDeleteNode,
}: PropertyPanelProps) {
  const [cycleError, setCycleError] = useState("");
  const [functions, setFunctions] = useState<FunctionInfo[]>([]);

  useEffect(() => {
    pluginsApi
      .listFunctions()
      .then(setFunctions)
      .catch(() => setFunctions([]));
  }, []);

  if (!node) {
    return (
      <aside className="property-panel" data-testid="property-panel">
        <p className="palette__title">属性面板</p>
        <DocInterfaceEditor doc={doc} readonly={readonly} onUpdate={onUpdate} />
        <p className="property-panel__hint">未选中节点</p>
      </aside>
    );
  }

  const updateNode = (patch: Partial<TreeNode>) => {
    if (readonly) return;
    onUpdate({ ...doc, nodes: { ...doc.nodes, [node.id]: { ...node, ...patch } } });
  };

  const setField = (key: string, value: string) => {
    updateNode({ fields: { ...node.fields, [key]: value } });
  };

  const free = freeRoots(doc);
  const mounts = slotFields(node);

  const slotOptions = (childId: string | null): ComboboxOption[] => {
    const ids: string[] = [];
    if (childId && childId in doc.nodes) ids.push(childId);
    for (const fid of free) {
      if (fid !== childId) ids.push(fid);
    }
    return [
      { value: "", label: "（空）" },
      ...ids.map((id) => ({ value: id, label: nodeLabel(doc, id) })),
    ];
  };

  const refTargetOptions: ComboboxOption[] = [
    { value: "", label: "（选择文档）" },
    ...docNames.filter((n) => n !== doc.tree).map((n) => ({ value: n, label: n })),
  ];

  const functionOptions: ComboboxOption[] = functions.map((f) => ({
    value: f.full_name,
    label: f.full_name,
    description: f.description,
  }));

  const handleSlotChange = (index: number, value: string) => {
    if (value === "") {
      onUpdate(detachSlot(doc, node.id, index));
    } else {
      onUpdate(setSlot(doc, node.id, index, value));
    }
  };

  const addSequenceSlot = () => {
    updateNode({ actions: [...(node.actions ?? []), ""] });
  };

  const addBranch = () => {
    updateNode({ branches: [...(node.branches ?? []), { when: "", action: "" }] });
  };

  const updateBranch = (i: number, patch: Partial<BranchRow>) => {
    const branches = (node.branches ?? []).map((b, j) => (j === i ? { ...b, ...patch } : b));
    updateNode({ branches });
  };

  const removeBranch = (i: number) => {
    updateNode({ branches: (node.branches ?? []).filter((_, j) => j !== i) });
  };

  const handleRefTarget = (target: string) => {
    if (wouldCreateCycle(target, doc.tree, refTargetsOf)) {
      setCycleError(`引用「${target}」形成跨文档循环`);
      return;
    }
    setCycleError("");
    updateNode({ target });
    if (target) onLoadRefMeta(target);
  };

  const setArg = (i: number, value: string) => {
    const args = [...(node.args ?? [])];
    while (args.length <= i) args.push("");
    args[i] = value;
    updateNode({ args });
  };

  const setReturnName = (i: number, name: string) => {
    const returns = { ...(node.returns ?? {}) };
    const keys = Object.keys(returns);
    const oldType = returns[keys[i]] ?? "str";
    const next: Record<string, string> = {};
    keys.forEach((k, j) => {
      next[j === i && name.trim() ? name.trim() : k] = returns[k];
    });
    if (!name.trim() && keys[i] !== undefined) {
      delete next[keys[i]];
      updateNode({ returns: next });
      return;
    }
    if (keys[i] === undefined) {
      if (name.trim()) next[name.trim()] = oldType;
    }
    updateNode({ returns: next });
  };

  const setReturnType = (i: number, type: string) => {
    const returns = { ...(node.returns ?? {}) };
    const key = Object.keys(returns)[i];
    if (key !== undefined) {
      returns[key] = type;
      updateNode({ returns });
    }
  };

  const meta = node.type === "ref" && node.target ? refMeta[node.target] : undefined;
  const isRoot = node.type === "Root";

  return (
    <aside className="property-panel" data-testid="property-panel" data-node-id={node.id}>
      <p className="palette__title">属性面板</p>
      <DocInterfaceEditor doc={doc} readonly={readonly} onUpdate={onUpdate} />
      <div className="property-panel__header">
        <span className="property-panel__type" data-testid="node-type-badge">
          {node.type}
        </span>
        <span className="property-panel__id">{node.id}</span>
      </div>
      <TextField
        label="节点名称"
        value={node.name}
        disabled={readonly}
        onChange={(e) => updateNode({ name: e.target.value })}
        placeholder="画布显示名"
      />

      {(node.type === "Sequence" || mounts.length > 0) ? (
        <div className="property-panel__section" data-testid="slot-editor">
          <p className="property-panel__section-title">槽位挂载</p>
          {mounts.map((m, index) => (
            <div key={`${m.field}-${index}`} className="slot-row">
              <Combobox
                label={m.label}
                value={m.childId ?? ""}
                options={slotOptions(m.childId)}
                disabled={readonly}
                dataTestid={`slot-${node.id}-${index}`}
                onChange={(value) => handleSlotChange(index, value)}
              />
            </div>
          ))}
          {node.type === "Sequence" && !readonly ? (
            <button
              type="button"
              className="slot-row__add"
              onClick={addSequenceSlot}
              data-testid={`add-slot-${node.id}`}
            >
              + 增加槽位
            </button>
          ) : null}
        </div>
      ) : null}

      {node.type === "Branch" ? (
        <div className="property-panel__section" data-testid="branch-editor">
          <p className="property-panel__section-title">分支</p>
          {(node.branches ?? []).map((b, i) => (
            <div key={i} className="branch-row" data-testid={`branch-row-${i}`}>
              {b.otherwise ? (
                <span className="property-panel__type">otherwise</span>
              ) : (
                <TextField
                  label="条件 when"
                  value={b.when ?? ""}
                  disabled={readonly}
                  onChange={(e) => updateBranch(i, { when: e.target.value })}
                />
              )}
              <Combobox
                label="分支动作"
                value={(b.action ?? b.otherwise) || ""}
                options={slotOptions((b.action ?? b.otherwise) || null)}
                disabled={readonly}
                onChange={(value) =>
                  updateBranch(i, { action: value || undefined, otherwise: undefined })
                }
              />
              {!readonly ? (
                <>
                  <button
                    type="button"
                    className="slot-row__add"
                    onClick={() => updateBranch(i, b.otherwise ? { otherwise: undefined } : { otherwise: "" })}
                  >
                    切换 otherwise
                  </button>
                  <button
                    type="button"
                    className="slot-row__add slot-row__add--danger"
                    onClick={() => removeBranch(i)}
                    data-testid={`branch-remove-${node.id}-${i}`}
                  >
                    删除分支
                  </button>
                </>
              ) : null}
            </div>
          ))}
          {!readonly ? (
          <button
            type="button"
            className="slot-row__add"
            onClick={addBranch}
            data-testid={`add-branch-${node.id}`}
          >
            + 添加分支
          </button>
        ) : null}
        </div>
      ) : null}

      {(SCALAR_FIELDS[node.type] ?? []).length > 0 ? (
        <div className="property-panel__section">
          {SCALAR_FIELDS[node.type].map((def) => (
            <TextField
              key={def.key}
              label={def.label}
              value={node.fields[def.key] ?? ""}
              placeholder={def.placeholder}
              disabled={readonly}
              data-testid={`field-${node.id}-${def.key}`}
              onChange={(e) => setField(def.key, e.target.value)}
            />
          ))}
        </div>
      ) : null}

      {node.type === "ref" ? (
        <div className="property-panel__section" data-testid="ref-editor">
          <p className="property-panel__section-title">引用参数</p>
          <Combobox
            label="目标文档"
            value={node.target ?? ""}
            options={refTargetOptions}
            disabled={readonly}
            dataTestid={`ref-target-${node.id}`}
            onChange={handleRefTarget}
          />
          {cycleError ? (
            <p className="error-message" data-testid="ref-cycle-error">
              {cycleError}
            </p>
          ) : null}
          {!node.target ? (
            <p className="property-panel__hint">选择目标文档后配置入参/出参</p>
          ) : !meta ? (
            <p className="property-panel__hint" data-testid="ref-loading">
              正在加载目标文档参数…
            </p>
          ) : null}
          {meta ? (
            <>
              {Object.keys(meta.inputs).map((inp, i) => (
                <TextField
                  key={`in-${inp}`}
                  label={`入参 ${inp}（${meta.inputs[inp]}）`}
                  value={(node.args ?? [])[i] ?? ""}
                  placeholder="本树变量名或字面量"
                  disabled={readonly}
                  data-testid={`ref-arg-${node.id}-${i}`}
                  onChange={(e) => setArg(i, e.target.value)}
                />
              ))}
              {meta.outputs.map((out, i) => (
                <div key={`out-${out}`} className="slot-row">
                  <span className="slot-row__label">出参 {out}</span>
                  <TextField
                    label="接收参数名"
                    value={Object.keys(node.returns ?? {})[i] ?? ""}
                    disabled={readonly}
                    data-testid={`ref-return-name-${node.id}-${i}`}
                    onChange={(e) => setReturnName(i, e.target.value)}
                  />
                  <select
                    className="text-field__input"
                    value={Object.values(node.returns ?? {})[i] ?? "str"}
                    disabled={readonly}
                    data-testid={`ref-return-type-${node.id}-${i}`}
                    onChange={(e) => setReturnType(i, e.target.value)}
                  >
                    {TYPE_TOKENS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </>
          ) : null}
        </div>
      ) : null}

      {node.type === "FunctionCall" ? (
        <div className="property-panel__section" data-testid="function-call-editor">
          <p className="property-panel__section-title">函数调用</p>
          <Combobox
            label="函数名"
            value={node.function ?? ""}
            options={functionOptions}
            disabled={readonly}
            placeholder="插件注册函数名（如 compute.add）"
            onChange={(value) => updateNode({ function: value })}
          />
          <p className="property-panel__section-title">实参（按序对应函数入参）</p>
          {(node.args ?? []).map((a, i) => (
            <TextField
              key={`fc-arg-${i}`}
              label={`实参 ${i + 1}`}
              value={a}
              disabled={readonly}
              onChange={(e) => setArg(i, e.target.value)}
              placeholder="变量名或字面量"
            />
          ))}
          {!readonly ? (
            <button
              type="button"
              className="slot-row__add"
              onClick={() => updateNode({ args: [...(node.args ?? []), ""] })}
            >
              添加实参
            </button>
          ) : null}
          <p className="property-panel__section-title">返回值（接收名 → 类型）</p>
          {Object.keys(node.returns ?? {}).map((k, i) => (
            <div key={`fc-return-${k}`} className="slot-row">
              <TextField
                label="接收参数名"
                value={k}
                disabled={readonly}
                onChange={(e) => setReturnName(i, e.target.value)}
              />
              <select
                className="text-field__input"
                value={(node.returns ?? {})[k] ?? "str"}
                disabled={readonly}
                onChange={(e) => setReturnType(i, e.target.value)}
              >
                {TYPE_TOKENS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          ))}
          {!readonly ? (
            <button
              type="button"
              className="slot-row__add"
              onClick={() =>
                updateNode({
                  returns: {
                    ...(node.returns ?? {}),
                    [`返回值${Object.keys(node.returns ?? {}).length + 1}`]: "str",
                  },
                })
              }
            >
              添加返回值
            </button>
          ) : null}
        </div>
      ) : null}

      {!readonly ? (
        <div className="property-panel__section">
          <button
            type="button"
            className="slot-row__add slot-row__add--danger"
            data-testid="delete-node"
            disabled={isRoot}
            onClick={() => onDeleteNode(node.id, false)}
          >
            删除此节点（子节点各自成游离树）
          </button>
          <button
            type="button"
            className="slot-row__add slot-row__add--danger"
            data-testid="delete-subtree"
            disabled={isRoot}
            onClick={() => onDeleteNode(node.id, true)}
          >
            删除子树（连带后代）
          </button>
        </div>
      ) : null}
    </aside>
  );
}