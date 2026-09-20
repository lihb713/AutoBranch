import { useState } from "react";
import { Button } from "../../components/Button";

type RunInputDialogProps = {
  treeName: string;
  inputs: Record<string, string>;
  onConfirm: (inputs: Record<string, unknown>) => void;
  onCancel: () => void;
};

function coerceForType(type: string, raw: string): unknown {
  if (type === "int") {
    const n = Number(raw);
    return Number.isNaN(n) ? raw : Math.trunc(n);
  }
  if (type === "float") {
    const n = Number(raw);
    return Number.isNaN(n) ? raw : n;
  }
  if (type === "bool") {
    return raw === "true";
  }
  return raw;
}

/** 执行入参对话框（Change A 任务 5.2）：按声明类型渲染输入框，仅可构造类型调用。 */
export function RunInputDialog({ treeName, inputs, onConfirm, onCancel }: RunInputDialogProps) {
  const entries = Object.entries(inputs);
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(entries.map(([name]) => [name, ""])),
  );
  const [bools, setBools] = useState<Record<string, boolean>>({});

  const handleSubmit = () => {
    const payload: Record<string, unknown> = {};
    for (const [name, type] of entries) {
      if (type === "bool") {
        payload[name] = bools[name] ?? false;
      } else {
        payload[name] = coerceForType(type, values[name] ?? "");
      }
    }
    onConfirm(payload);
  };

  return (
    <div className="run-dialog" data-testid="run-input-dialog">
      <p className="run-dialog__title">执行「{treeName}」——提供入参</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSubmit();
        }}
      >
        {entries.map(([name, type]) => (
          <label key={name} className="run-dialog__field" data-testid={`input-field-${name}`}>
            <span className="run-dialog__label">
              {name} <span className="muted">({type})</span>
            </span>
            {type === "bool" ? (
              <input
                type="checkbox"
                className="run-dialog__input"
                data-testid={`input-value-${name}`}
                checked={bools[name] ?? false}
                onChange={(e) => setBools((prev) => ({ ...prev, [name]: e.target.checked }))}
              />
            ) : (
              <input
                type="text"
                className="run-dialog__input"
                data-testid={`input-value-${name}`}
                value={values[name] ?? ""}
                onChange={(e) =>
                  setValues((prev) => ({ ...prev, [name]: e.target.value }))
                }
              />
            )}
          </label>
        ))}
        <div className="run-dialog__actions">
          <Button type="button" variant="ghost" onClick={onCancel} data-testid="run-dialog-cancel">
            取消
          </Button>
          <Button type="submit" data-testid="run-dialog-confirm">
            开始执行
          </Button>
        </div>
      </form>
    </div>
  );
}