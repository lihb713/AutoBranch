import { useEffect, useState } from "react";
import { pluginsApi } from "../../api/plugins";
import { Combobox, type ComboboxOption } from "../../components/Combobox";
import { HighlightedField } from "../../components/HighlightedField";
import { TextField } from "../../components/TextField";
import type { FunctionInfo } from "../../types/plugin";
import { schemaTypeToToken, TYPE_TOKENS } from "./tokens";
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

type FieldDef = { key: string; label: string; placeholder?: string };

/** 各节点类型的标量字段定义（分组渲染，组名 = 组标题）。 */
const FIELD_GROUPS: Record<string, { title: string; fields: FieldDef[] }[]> = {
  Step: [{ title: "验证条件", fields: [{ key: "expect", label: "验证 expect", placeholder: "如：出现\"工作台\"" }] }],
  Action: [{ title: "操作描述", fields: [{ key: "description", label: "操作描述", placeholder: "如：点击\"登录\"" }] }],
  IfThenElse: [{ title: "判断条件", fields: [{ key: "if", label: "判断 if", placeholder: "如：存在\"下载成功\"" }] }],
  LoopUntil: [
    {
      title: "循环参数",
      fields: [
        { key: "until", label: "终止条件 until", placeholder: "如：出现\"最后一页\"" },
        { key: "max", label: "循环上限 max", placeholder: "如：50" },
      ],
    },
  ],
  Retry: [{ title: "重试参数", fields: [{ key: "max", label: "重试上限 max", placeholder: "如：3" }] }],
};

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

  const selectedFunc =
    node.type === "FunctionCall"
      ? functions.find((f) => f.full_name === node.function)
      : undefined;
  const schema = (selectedFunc?.parameters ?? {}) as {
    properties?: Record<string, { type?: string }>;
    required?: string[];
  };
  const fcParams = schema.properties
    ? [...(schema.required ?? []), ...Object.keys(schema.properties).filter((k) => !(schema.required ?? []).includes(k))]
    : [];

  const renderSlotGroup = (title: string, mountList: typeof mounts, withAddSlot = false) => (
    <section className="prop-group" data-testid="prop-group-slot">
      <h4 className="prop-group__title">{title}</h4>
      {mountList.map((m, index) => (
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
      {withAddSlot && !readonly ? (
        <button
          type="button"
          className="slot-row__add"
          onClick={addSequenceSlot}
          data-testid={`add-slot-${node.id}`}
        >
          + 增加槽位
        </button>
      ) : null}
    </section>
  );

  const renderFieldGroup = (title: string, defs: FieldDef[]) => (
    <section className="prop-group" data-testid={`prop-group-${title}`}>
      <h4 className="prop-group__title">{title}</h4>
      {defs.map((def) => (
        <HighlightedField
          key={def.key}
          label={def.label}
          value={node.fields[def.key] ?? ""}
          placeholder={def.placeholder}
          disabled={readonly}
          data-testid={`field-${node.id}-${def.key}`}
          onChange={(e) => setField(def.key, e.target.value)}
        />
      ))}
    </section>
  );

  const renderBranchGroup = () => (
    <section className="prop-group" data-testid="prop-group-branch">
      <h4 className="prop-group__title">分支</h4>
      {(node.branches ?? []).map((b, i) => (
        <div key={i} className="branch-row" data-testid={`branch-row-${i}`}>
          {b.otherwise ? (
            <span className="property-panel__type">otherwise</span>
          ) : (
            <HighlightedField
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
    </section>
  );

  const renderRefGroup = () => (
    <>
      <section className="prop-group" data-testid="prop-group-ref-target">
        <h4 className="prop-group__title">引用目标</h4>
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
      </section>
      <section className="prop-group" data-testid="prop-group-ref-args">
        <h4 className="prop-group__title">入参</h4>
        {!node.target ? (
          <p className="property-panel__hint">选择目标文档后配置入参/出参</p>
        ) : !meta ? (
          <p className="property-panel__hint" data-testid="ref-loading">
            正在加载目标文档参数…
          </p>
        ) : (
          Object.keys(meta.inputs).map((inp, i) => (
            <HighlightedField
              key={`in-${inp}`}
              label={`入参 ${inp}（${meta.inputs[inp]}）`}
              value={(node.args ?? [])[i] ?? ""}
              placeholder="本树变量名或字面量"
              disabled={readonly}
              data-testid={`ref-arg-${node.id}-${i}`}
              onChange={(e) => setArg(i, e.target.value)}
            />
          ))
        )}
      </section>
      {meta ? (
        <section className="prop-group" data-testid="prop-group-ref-returns">
          <h4 className="prop-group__title">出参</h4>
          {meta.outputs.map((out, i) => (
            <div key={`out-${out}`} className="slot-row">
              <span className="slot-row__label">出参 {out}</span>
              <HighlightedField
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
        </section>
      ) : null}
    </>
  );

  const renderFunctionCallGroup = () => (
    <>
      <section className="prop-group" data-testid="prop-group-fc-function">
        <h4 className="prop-group__title">函数</h4>
        <Combobox
          label="函数名"
          value={node.function ?? ""}
          options={functionOptions}
          disabled={readonly}
          placeholder="插件注册函数名（如 compute.add）"
          onChange={(value) => updateNode({ function: value })}
        />
      </section>
      <section className="prop-group" data-testid="prop-group-fc-args">
        <h4 className="prop-group__title">入参</h4>
        {!selectedFunc ? (
          <p className="property-panel__hint">选择函数后自动列出参数</p>
        ) : (
          fcParams.map((p, i) => (
            <HighlightedField
              key={`fc-in-${p}`}
              label={`入参 ${p}（${schemaTypeToToken(schema.properties?.[p]?.type)}）`}
              value={(node.args ?? [])[i] ?? ""}
              placeholder="变量名或字面量"
              disabled={readonly}
              data-testid={`fc-arg-${node.id}-${i}`}
              onChange={(e) => setArg(i, e.target.value)}
            />
          ))
        )}
      </section>
      <section className="prop-group" data-testid="prop-group-fc-returns">
        <h4 className="prop-group__title">返回值</h4>
        {!selectedFunc ? (
          <p className="property-panel__hint">选择函数后自动列出返回值</p>
        ) : (
          selectedFunc.returns.map((r, i) => (
            <div key={`fc-out-${r}`} className="slot-row">
              <span className="slot-row__label">返回值 {r}</span>
              <HighlightedField
                label="接收参数名"
                value={Object.keys(node.returns ?? {})[i] ?? ""}
                disabled={readonly}
                data-testid={`fc-return-name-${node.id}-${i}`}
                onChange={(e) => setReturnName(i, e.target.value)}
              />
              <select
                className="text-field__input"
                value={Object.values(node.returns ?? {})[i] ?? "str"}
                disabled={readonly}
                data-testid={`fc-return-type-${node.id}-${i}`}
                onChange={(e) => setReturnType(i, e.target.value)}
              >
                {TYPE_TOKENS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          ))
        )}
      </section>
    </>
  );

  let groups: JSX.Element[];
  switch (node.type) {
    case "Sequence":
      groups = [renderSlotGroup("槽位", mounts, true)];
      break;
    case "Step":
      groups = [
        renderFieldGroup("验证条件", FIELD_GROUPS.Step[0].fields),
        renderSlotGroup("槽位", mounts),
      ];
      break;
    case "Action":
      groups = [renderFieldGroup("操作描述", FIELD_GROUPS.Action[0].fields)];
      break;
    case "IfThenElse":
      groups = [
        renderFieldGroup("判断条件", FIELD_GROUPS.IfThenElse[0].fields),
        renderSlotGroup("槽位", mounts),
      ];
      break;
    case "Branch":
      groups = [
        renderSlotGroup("前置操作", mounts.slice(0, 1)),
        renderBranchGroup(),
      ];
      break;
    case "Retry":
      groups = [
        renderFieldGroup("重试参数", FIELD_GROUPS.Retry[0].fields),
        renderSlotGroup("槽位", mounts),
      ];
      break;
    case "LoopUntil":
      groups = [
        renderFieldGroup("循环参数", FIELD_GROUPS.LoopUntil[0].fields),
        renderSlotGroup("槽位", mounts),
      ];
      break;
    case "ref":
      groups = [renderRefGroup()];
      break;
    case "FunctionCall":
      groups = [renderFunctionCallGroup()];
      break;
    default:
      groups = [renderSlotGroup("槽位", mounts)];
  }

  return (
    <aside className="property-panel" data-testid="property-panel" data-node-id={node.id}>
      <p className="palette__title">属性面板</p>
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

      <div className="node-props" data-testid="node-props">
        {groups.map((g, i) => (
          <div key={i} className="node-props__group">
            {g}
          </div>
        ))}
      </div>

      {!readonly ? (
        <div className="property-panel__section property-panel__danger-zone">
          <button
            type="button"
            className="slot-row__add slot-row__add--danger"
            data-testid="delete-node"
            disabled={isRoot}
            onClick={() => onDeleteNode(node.id, false)}
          >
            删除此节点
          </button>
          <button
            type="button"
            className="slot-row__add slot-row__add--danger"
            data-testid="delete-subtree"
            disabled={isRoot}
            onClick={() => onDeleteNode(node.id, true)}
          >
            删除子树
          </button>
        </div>
      ) : null}
    </aside>
  );
}