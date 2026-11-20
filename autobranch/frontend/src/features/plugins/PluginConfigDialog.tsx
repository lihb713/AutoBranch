import { useEffect, useState } from "react";
import { pluginsApi } from "../../api/plugins";
import { Button } from "../../components/Button";
import { CheckboxField } from "../../components/CheckboxField";
import { ErrorMessage } from "../../components/ErrorMessage";
import { TextField } from "../../components/TextField";
import type { ConfigSchemaItem } from "../../types/plugin";

type Props = {
  pluginName: string;
  schema: ConfigSchemaItem[];
  onClose: () => void;
  onSaved?: () => void;
};

export function PluginConfigDialog({ pluginName, schema, onClose, onSaved }: Props) {
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    pluginsApi
      .getConfig(pluginName)
      .then((config) => {
        const initial: Record<string, unknown> = {};
        for (const item of schema) {
          initial[item.key] = config[item.key] ?? item.default ?? "";
        }
        setValues(initial);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [pluginName, schema]);

  const save = async () => {
    setError(null);
    for (const item of schema) {
      if (item.required && (values[item.key] === "" || values[item.key] === undefined)) {
        setError(`请填写「${item.label}」`);
        return;
      }
    }
    setSaving(true);
    try {
      await pluginsApi.updateConfig(pluginName, values);
      onSaved?.();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="dialog-overlay" data-testid="plugin-config-dialog">
      <div className="dialog" role="dialog" aria-label={`配置插件 ${pluginName}`}>
        <div className="dialog-header">
          <h2>配置插件 {pluginName}</h2>
          <button className="link" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        <div className="dialog-body">
          {loading ? <p className="muted">加载中…</p> : null}
          {schema.map((item) => (
            <div className="form-field" key={item.key}>
              <label htmlFor={`cfg-${item.key}`}>
                {item.label}
                {item.required ? <span className="required"> *</span> : null}
              </label>
              {item.type === "boolean" ? (
                <CheckboxField
                  id={`cfg-${item.key}`}
                  label={item.label}
                  checked={Boolean(values[item.key])}
                  onChange={(e) =>
                    setValues((prev) => ({ ...prev, [item.key]: e.target.checked }))
                  }
                />
              ) : (
                <TextField
                  id={`cfg-${item.key}`}
                  label={`${item.label}${item.required ? " *" : ""}`}
                  type={item.type === "number" ? "number" : "text"}
                  value={String(values[item.key] ?? "")}
                  onChange={(e) =>
                    setValues((prev) => ({
                      ...prev,
                      [item.key]:
                        item.type === "number" ? Number(e.target.value) : e.target.value,
                    }))
                  }
                />
              )}
              {item.description ? <small className="muted">{item.description}</small> : null}
            </div>
          ))}
          {error ? <ErrorMessage message={error} /> : null}
        </div>
        <div className="dialog-footer">
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button onClick={save} disabled={saving || loading}>
            {saving ? "保存中…" : "保存"}
          </Button>
        </div>
      </div>
    </div>
  );
}
