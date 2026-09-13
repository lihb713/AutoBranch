import type { TreeDoc } from "./treeModel";

const TYPE_TOKENS = ["str", "int", "float", "bool", "page_ref"];

type DocInterfaceEditorProps = {
  doc: TreeDoc;
  readonly?: boolean;
  onUpdate: (doc: TreeDoc) => void;
};

/** 文档级接口编辑：`inputs`（名→类型）与 `outputs`（名列表），ref 参数对齐依据。 */
export function DocInterfaceEditor({ doc, readonly = false, onUpdate }: DocInterfaceEditorProps) {
  const updateDoc = (patch: Partial<TreeDoc>) => onUpdate({ ...doc, ...patch });

  const setInputName = (oldKey: string, newKey: string) => {
    const inputs = { ...doc.inputs };
    const type = inputs[oldKey];
    delete inputs[oldKey];
    if (newKey.trim()) inputs[newKey.trim()] = type;
    updateDoc({ inputs });
  };

  const setInputType = (key: string, type: string) => {
    updateDoc({ inputs: { ...doc.inputs, [key]: type } });
  };

  const addInput = () => {
    const base = `入参${Object.keys(doc.inputs).length + 1}`;
    let name = base;
    let i = 2;
    while (name in doc.inputs) {
      name = `${base}${i}`;
      i += 1;
    }
    updateDoc({ inputs: { ...doc.inputs, [name]: "str" } });
  };

  const removeInput = (key: string) => {
    const inputs = { ...doc.inputs };
    delete inputs[key];
    updateDoc({ inputs });
  };

  const setOutput = (i: number, name: string) => {
    updateDoc({ outputs: doc.outputs.map((o, j) => (j === i ? name : o)) });
  };

  const addOutput = () => {
    const base = `出参${doc.outputs.length + 1}`;
    let name = base;
    let i = 2;
    while (doc.outputs.includes(name)) {
      name = `${base}${i}`;
      i += 1;
    }
    updateDoc({ outputs: [...doc.outputs, name] });
  };

  const removeOutput = (i: number) => {
    updateDoc({ outputs: doc.outputs.filter((_, j) => j !== i) });
  };

  return (
    <div className="property-panel__section" data-testid="doc-interface">
      <p className="property-panel__section-title">文档接口</p>
      <p className="property-panel__hint">树名：{doc.tree || "（未命名）"}</p>

      <div data-testid="doc-inputs">
        <p className="slot-row__label">入参 inputs（名：类型，ref 按此填 args）</p>
        {Object.entries(doc.inputs).map(([name, type]) => (
          <div key={name} className="slot-row" data-testid={`doc-input-${name}`}>
            <input
              className="text-field__input"
              value={name}
              disabled={readonly}
              data-testid={`doc-input-name-${name}`}
              onChange={(e) => setInputName(name, e.target.value)}
            />
            <select
              className="text-field__input"
              value={type}
              disabled={readonly}
              data-testid={`doc-input-type-${name}`}
              onChange={(e) => setInputType(name, e.target.value)}
            >
              {TYPE_TOKENS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            {!readonly ? (
              <button
                type="button"
                className="slot-row__add slot-row__add--danger"
                data-testid={`doc-input-remove-${name}`}
                onClick={() => removeInput(name)}
              >
                删除
              </button>
            ) : null}
          </div>
        ))}
        {!readonly ? (
          <button
            type="button"
            className="slot-row__add"
            data-testid="doc-input-add"
            onClick={addInput}
          >
            + 添加入参
          </button>
        ) : null}
      </div>

      <div data-testid="doc-outputs">
        <p className="slot-row__label">出参 outputs（名列表，ref 按此填 returns）</p>
        {doc.outputs.map((name, i) => (
          <div key={i} className="slot-row" data-testid={`doc-output-${i}`}>
            <input
              className="text-field__input"
              value={name}
              disabled={readonly}
              data-testid={`doc-output-name-${i}`}
              onChange={(e) => setOutput(i, e.target.value)}
            />
            {!readonly ? (
              <button
                type="button"
                className="slot-row__add slot-row__add--danger"
                data-testid={`doc-output-remove-${i}`}
                onClick={() => removeOutput(i)}
              >
                删除
              </button>
            ) : null}
          </div>
        ))}
        {!readonly ? (
          <button
            type="button"
            className="slot-row__add"
            data-testid="doc-output-add"
            onClick={addOutput}
          >
            + 添加出参
          </button>
        ) : null}
      </div>
    </div>
  );
}