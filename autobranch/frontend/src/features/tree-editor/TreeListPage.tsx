import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../api/request";
import { runsApi } from "../../api/runs";
import { treesApi } from "../../api/trees";
import { typesApi } from "../../api/types";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorMessage } from "../../components/ErrorMessage";
import type { TreeOut } from "../../types/tree";
import { RunInputDialog } from "../runs/RunInputDialog";
import { parseDoc } from "./treeModel";

function formatTime(value: string): string {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("zh-CN");
}

export function TreeListPage() {
  const navigate = useNavigate();
  const [trees, setTrees] = useState<TreeOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [constructible, setConstructible] = useState<Set<string>>(new Set());
  const [pendingTree, setPendingTree] = useState<TreeOut | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    typesApi
      .listTypes()
      .then((list) => setConstructible(new Set(list.filter((t) => t.constructible).map((t) => t.token))))
      .catch(() => setConstructible(new Set(["str", "int", "float", "bool"])));
  }, []);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    treesApi
      .listTrees()
      .then((list) => setTrees(list))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "加载列表失败");
      })
      .finally(() => setLoading(false));
  }, []);

  const refetchList = useCallback(() => {
    treesApi
      .listTrees()
      .then((list) => setTrees(list))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "加载列表失败");
      });
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const handleDelete = useCallback(
    async (tree: TreeOut) => {
      setError(null);
      try {
        await treesApi.deleteTree(tree.id);
        setTrees((prev) => prev.filter((t) => t.id !== tree.id));
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          setError(`行为树「${tree.name}」不存在，列表已刷新`);
          refetchList();
        } else {
          setError(err instanceof Error ? err.message : "删除失败");
        }
      }
    },
    [refetchList],
  );

  const runTree = useCallback(
    async (tree: TreeOut, inputs?: Record<string, unknown>) => {
      setError(null);
      setPendingTree(null);
      try {
        const { run_id } = await runsApi.runTree(tree.id, inputs);
        navigate(`/runs/${run_id}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "触发执行失败");
      }
    },
    [navigate],
  );

  const handleRunClick = useCallback(
    (tree: TreeOut) => {
      const declared = Object.keys(tree.inputs ?? {});
      if (declared.length === 0) {
        void runTree(tree);
        return;
      }
      const nonConstructible = declared.filter((name) => !constructible.has(tree.inputs[name]));
      if (nonConstructible.length > 0) {
        return; // 含不可构造入参 → 不渲染执行按钮（防御性）
      }
      setPendingTree(tree);
    },
    [constructible, runTree],
  );

  const canRunDirectly = (tree: TreeOut) =>
    Object.keys(tree.inputs ?? {}).every((name) => constructible.has(tree.inputs[name]));

  const handleImport = useCallback(
    async (file: File) => {
      setError(null);
      setImporting(true);
      try {
        const text = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result));
          reader.onerror = () => reject(reader.error ?? new Error("读取文件失败"));
          reader.readAsText(file);
        });
        const parsed = parseDoc(text); // 统一槽位 DSL 校验 + 取树名
        await treesApi.createTree({ name: parsed.tree, content: text });
        refetchList();
      } catch (err) {
        setError(err instanceof Error ? `导入失败：${err.message}` : "导入失败");
      } finally {
        setImporting(false);
      }
    },
    [refetchList],
  );

  return (
    <section className="tree-list-page" data-testid="tree-list-page">
      <header className="page-header">
        <h1 className="page-title">行为树</h1>
      </header>

      {error ? <ErrorMessage message={error} /> : null}

      <div className="tree-list-toolbar" data-testid="tree-list-toolbar">
        <Button
          variant="ghost"
          onClick={() => fileInputRef.current?.click()}
          disabled={importing}
          data-testid="import-tree"
        >
          {importing ? "导入中…" : "导入文档"}
        </Button>
        <Button onClick={() => navigate("/editor")} data-testid="new-tree">
          新建行为树
        </Button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".yaml,.yml,.md,.txt"
        data-testid="import-file"
        className="visually-hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleImport(file);
          e.target.value = "";
        }}
      />

      {loading ? (
        <div className="page-loading">加载中…</div>
      ) : trees.length === 0 ? (
        <EmptyState title="还没有行为树" hint="点击「新建行为树」创建第一份行为树文档" />
      ) : (
        <table className="tree-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {trees.map((tree) => (
              <tr
                key={tree.id}
                className="tree-table__row"
                data-testid={`tree-row-${tree.id}`}
                onClick={() => navigate(`/editor/${tree.id}`)}
              >
                <td>{tree.name}</td>
                <td>{formatTime(tree.updated_at)}</td>
                <td>
                  <div className="tree-table__actions" onClick={(e) => e.stopPropagation()}>
                    <Button
                      variant="ghost"
                      onClick={() => navigate(`/editor/${tree.id}`)}
                      data-testid={`edit-${tree.id}`}
                    >
                      编辑
                    </Button>
                    {canRunDirectly(tree) ? (
                      <Button
                        variant="ghost"
                        onClick={() => handleRunClick(tree)}
                        data-testid={`run-${tree.id}`}
                      >
                        执行
                      </Button>
                    ) : null}
                    <Button variant="danger" onClick={() => handleDelete(tree)} data-testid={`delete-${tree.id}`}>
                      删除
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {pendingTree ? (
        <RunInputDialog
          treeName={pendingTree.name}
          inputs={pendingTree.inputs}
          onConfirm={(inputs) => void runTree(pendingTree, inputs)}
          onCancel={() => setPendingTree(null)}
        />
      ) : null}
    </section>
  );
}