import { useState } from "react";

import { Button } from "../../components/Button";
import { ErrorMessage } from "../../components/ErrorMessage";
import { TextField } from "../../components/TextField";
import type { TreeGroup } from "../../types/tree";

type TreeGroupManagerProps = {
  groups: TreeGroup[];
  onClose: () => void;
  onCreate: (name: string) => Promise<void>;
  onRename: (id: number, name: string) => Promise<void>;
  onDelete: (group: TreeGroup) => Promise<void>;
};

export function TreeGroupManager({
  groups,
  onClose,
  onCreate,
  onRename,
  onDelete,
}: TreeGroupManagerProps) {
  const [newName, setNewName] = useState("");
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div
        className="modal-panel group-manager"
        data-testid="group-manager"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h2 className="dialog-header">分组管理</h2>
        {error ? <ErrorMessage message={error} /> : null}
        <form
          className="group-manager__create"
          onSubmit={(event) => {
            event.preventDefault();
            const name = newName.trim();
            if (!name) return;
            void run(async () => {
              await onCreate(name);
              setNewName("");
            });
          }}
        >
          <TextField
            label="新分组名称"
            value={newName}
            data-testid="new-group-name"
            onChange={(event) => setNewName(event.target.value)}
            placeholder="如：开发环境"
          />
          <Button type="submit" disabled={busy || !newName.trim()} data-testid="create-group">
            新建分组
          </Button>
        </form>

        <table className="tree-table group-manager__table">
          <thead>
            <tr>
              <th>分组</th>
              <th>行为树数量</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <tr key={group.id} data-testid={`group-row-${group.id}`}>
                <td>
                  <TextField
                    label="名称"
                    value={edits[group.id] ?? group.name}
                    data-testid={`group-name-${group.id}`}
                    disabled={busy}
                    onChange={(event) =>
                      setEdits((prev) => ({ ...prev, [group.id]: event.target.value }))
                    }
                  />
                  {group.is_default ? <span className="muted">（默认）</span> : null}
                </td>
                <td>{group.tree_count}</td>
                <td>
                  <Button
                    variant="ghost"
                    disabled={busy}
                    data-testid={`group-save-${group.id}`}
                    onClick={() =>
                      void run(async () => {
                        const name = (edits[group.id] ?? group.name).trim();
                        if (!name) return;
                        await onRename(group.id, name);
                        setEdits((prev) => {
                          const next = { ...prev };
                          delete next[group.id];
                          return next;
                        });
                      })
                    }
                  >
                    保存
                  </Button>
                  <Button
                    variant="danger"
                    disabled={busy || group.is_default}
                    data-testid={`group-delete-${group.id}`}
                    onClick={() => void run(() => onDelete(group))}
                  >
                    删除
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="dialog-actions">
          <Button variant="ghost" onClick={onClose} data-testid="close-group-manager">
            关闭
          </Button>
        </div>
      </div>
    </div>
  );
}
