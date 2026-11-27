import { useState } from "react";

import { Button } from "../../components/Button";
import { ErrorMessage } from "../../components/ErrorMessage";
import { TextField } from "../../components/TextField";

type TreeGroupDialogProps = {
  title: string;
  initialName?: string;
  submitLabel?: string;
  onCancel: () => void;
  onSubmit: (name: string) => Promise<void>;
};

export function TreeGroupDialog({
  title,
  initialName = "",
  submitLabel = "保存",
  onCancel,
  onSubmit,
}: TreeGroupDialogProps) {
  const [name, setName] = useState(initialName);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const value = name.trim();
    if (!value) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit(value);
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" onMouseDown={onCancel}>
      <div
        className="modal-panel"
        data-testid="group-dialog"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h2 className="dialog-header">{title}</h2>
        {error ? <ErrorMessage message={error} /> : null}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <TextField
            label="分组名称"
            value={name}
            autoFocus
            data-testid="group-dialog-name"
            placeholder="如：生产环境"
            onChange={(event) => setName(event.target.value)}
          />
          <div className="dialog-actions">
            <Button
              type="submit"
              disabled={busy || !name.trim()}
              data-testid="group-dialog-submit"
            >
              {submitLabel}
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={busy}
              data-testid="group-dialog-cancel"
              onClick={onCancel}
            >
              取消
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
