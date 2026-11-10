import type { TreeDoc } from "./treeModel";
import { TYPE_TOKENS } from "./tokens";

type DocInterfaceEditorProps = {
  doc: TreeDoc;
  readonly?: boolean;
  onPatch: (patch: Partial<TreeDoc>) => void;
};

/** 文档级接口编辑：`inputs` / `outputs` 均为 `{名称: 类型}` 映射。 */
export function DocInterfaceEditor({ doc, readonly = false, onPatch }: DocInterfaceEditorProps) {
  const setInputName = (oldKey: string, newKey: string) => {
    const inputs = { ...doc.inputs };
    const type = inputs[oldKey];
    delete inputs[oldKey];
    if (newKey.trim()) inputs[newKey.trim()] = type;
    onPatch({ inputs });
  };

  const setInputType = (key: string, type: string) => {
    onPatch({ inputs: { ...doc.inputs, [key]: type } });
  };

  const addInput = () => {
    let i = 1;
    let name = `input${i}`;
    while (name in doc.inputs) {
      i += 1;
      name = `input${i}`;
    }
    onPatch({ inputs: { ...doc.inputs, [name]: "str" } });
  };

  const removeInput = (key: string) => {
    const inputs = { ...doc.inputs };
    delete inputs[key];
    onPatch({ inputs });
  };

  const setOutputName = (oldKey: string, newKey: string) => {
    const outputs = { ...doc.outputs };
    const type = outputs[oldKey];
    delete outputs[oldKey];
    if (newKey.trim()) outputs[newKey.trim()] = type;
    onPatch({ outputs });
  };

  const setOutputType = (key: string, type: string) => {
    onPatch({ outputs: { ...doc.outputs, [key]: type } });
  };

  const addOutput = () => {
    let i = 1;
    let name = `output${i}`;
    while (name in doc.outputs) {
      i += 1;
      name = `output${i}`;
    }
    onPatch({ outputs: { ...doc.outputs, [name]: "str" } });
  };

  const removeOutput = (key: string) => {
    const outputs = { ...doc.outputs };
    delete outputs[key];
    onPatch({ outputs });
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
        <p className="slot-row__label">出参 outputs（名：类型，ref 按此接收）</p>
        {Object.entries(doc.outputs).map(([name, type]) => (
          <div key={name} className="slot-row" data-testid={`doc-output-${name}`}>
            <input
              className="text-field__input"
              value={name}
              disabled={readonly}
              data-testid={`doc-output-name-${name}`}
              onChange={(e) => setOutputName(name, e.target.value)}
            />
            <select
              className="text-field__input"
              value={type}
              disabled={readonly}
              data-testid={`doc-output-type-${name}`}
              onChange={(e) => setOutputType(name, e.target.value)}
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
                data-testid={`doc-output-remove-${name}`}
                onClick={() => removeOutput(name)}
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
