import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../api/request";
import { runsApi } from "../../api/runs";
import { treesApi } from "../../api/trees";
import { typesApi } from "../../api/types";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorMessage } from "../../components/ErrorMessage";
import { HoverTooltip } from "../../components/HoverTooltip";
import type { TreeGroup, TreeOut } from "../../types/tree";
import { RunInputDialog } from "../runs/RunInputDialog";
import { TreeGroupDialog } from "./TreeGroupDialog";
import { parseDoc } from "./treeModel";

function formatTime(value: string): string {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("zh-CN");
}

function fileNameFor(name: string): string {
  const safe = name.replace(/[\\/:*?"<>|]/g, "_").trim() || "behavior-tree";
  return `${safe}.yaml`;
}

export function TreeListPage() {
  const navigate = useNavigate();
  const [trees, setTrees] = useState<TreeOut[]>([]);
  const [groups, setGroups] = useState<TreeGroup[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<number | "all">("all");
  const [collapsedGroupIds, setCollapsedGroupIds] = useState<Set<number>>(new Set());
  const [groupDialog, setGroupDialog] = useState<
    { mode: "create" } | { mode: "rename"; group: TreeGroup } | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [exportingId, setExportingId] = useState<number | null>(null);
  const [constructible, setConstructible] = useState<Set<string>>(new Set());
  const [pendingTree, setPendingTree] = useState<TreeOut | null>(null);
  const [creating, setCreating] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    typesApi
      .listTypes()
      .then((list) => setConstructible(new Set(list.filter((t) => t.constructible).map((t) => t.token))))
      .catch(() => setConstructible(new Set(["str", "int", "float", "bool"])));
  }, []);

  const fetchData = useCallback(async () => {
    const [list, groupList] = await Promise.all([
      treesApi.listTrees(),
      treesApi.listTreeGroups(),
    ]);
    setTrees(list);
    setGroups(groupList);
    setSelectedGroupId((current) => {
      if (current === "all") return current;
      return groupList.some((group) => group.id === current) ? current : "all";
    });
  }, []);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchData()
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "加载列表失败");
      })
      .finally(() => setLoading(false));
  }, [fetchData]);

  const refetchList = useCallback(() => {
    fetchData().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "加载列表失败");
    });
  }, [fetchData]);

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
    tree.status === "published" &&
    Object.keys(tree.inputs ?? {}).every((name) => constructible.has(tree.inputs[name]));

  const handleCreate = useCallback(async () => {
    setError(null);
    setCreating(true);
    try {
      const draft = await treesApi.createDraft(
        selectedGroupId === "all" ? undefined : selectedGroupId,
      );
      navigate(`/editor/${draft.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "新建失败");
    } finally {
      setCreating(false);
    }
  }, [navigate, selectedGroupId]);

  const handleExport = useCallback(async (tree: TreeOut) => {
    setError(null);
    setExportingId(tree.id);
    try {
      const detail = await treesApi.getTree(tree.id);
      const blob = new Blob([detail.content], {
        type: "application/x-yaml;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileNameFor(tree.name);
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? `导出失败：${err.message}` : "导出失败");
    } finally {
      setExportingId(null);
    }
  }, []);

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
        await treesApi.createTree({
          name: parsed.tree,
          content: text,
          group_id: selectedGroupId === "all" ? undefined : selectedGroupId,
        });
        refetchList();
      } catch (err) {
        setError(err instanceof Error ? `导入失败：${err.message}` : "导入失败");
      } finally {
        setImporting(false);
      }
    },
    [refetchList, selectedGroupId],
  );

  const handleMoveGroup = useCallback(
    async (tree: TreeOut, groupId: number) => {
      setError(null);
      try {
        await treesApi.moveTreeGroup(tree.id, groupId);
        await fetchData();
      } catch (err) {
        setError(err instanceof Error ? err.message : "移动分组失败");
      }
    },
    [fetchData],
  );

  const handleCreateGroup = useCallback(
    async (name: string) => {
      await treesApi.createTreeGroup(name);
      setGroupDialog(null);
      await fetchData();
    },
    [fetchData],
  );

  const handleRenameGroup = useCallback(
    async (id: number, name: string) => {
      await treesApi.renameTreeGroup(id, name);
      setGroupDialog(null);
      await fetchData();
    },
    [fetchData],
  );

  const handleDeleteGroup = useCallback(
    async (group: TreeGroup) => {
      setError(null);
      try {
        await treesApi.deleteTreeGroup(group.id);
        await fetchData();
      } catch (err) {
        setError(err instanceof Error ? err.message : "删除分组失败");
      }
    },
    [fetchData],
  );

  const toggleGroup = (groupId: number) => {
    setCollapsedGroupIds((previous) => {
      const next = new Set(previous);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  };

  const defaultGroupId = groups.find((group) => group.is_default)?.id;
  const visibleTrees =
    selectedGroupId === "all"
      ? trees
      : trees.filter((tree) => (tree.group_id ?? defaultGroupId) === selectedGroupId);
  const visibleGroups =
    selectedGroupId === "all"
      ? groups
      : groups.filter((group) => group.id === selectedGroupId);

  return (
    <section className="tree-list-page" data-testid="tree-list-page">
      <header className="page-header">
        <h1 className="page-title">行为树</h1>
      </header>

      {error ? <ErrorMessage message={error} /> : null}

      <div className="tree-list-toolbar" data-testid="tree-list-toolbar">
        <div className="tree-list-toolbar__group">
          <span className="tree-list-toolbar__group-label">分组</span>
          <select
            className="text-field__input tree-list-toolbar__select"
            value={selectedGroupId}
            data-testid="group-filter"
            onChange={(event) =>
              setSelectedGroupId(
                event.target.value === "all" ? "all" : Number(event.target.value),
              )
            }
          >
            <option value="all">全部分组</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}（{group.tree_count}）
              </option>
            ))}
          </select>
        </div>
        <Button
          variant="ghost"
          onClick={() => setGroupDialog({ mode: "create" })}
          data-testid="new-group"
        >
          新建分组
        </Button>
        <Button
          variant="ghost"
          onClick={() => fileInputRef.current?.click()}
          disabled={importing}
          data-testid="import-tree"
        >
          {importing ? "导入中…" : "导入文档"}
        </Button>
        <Button onClick={() => void handleCreate()} disabled={creating} data-testid="new-tree">
          {creating ? "创建中…" : "新建行为树"}
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
      ) : visibleGroups.length === 0 ? (
        <EmptyState
          title="还没有分组"
          hint="点击「新建分组」创建第一个分组"
        />
      ) : (
        <table className="tree-table tree-group-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>描述</th>
              <th>分组</th>
              <th>状态</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr>
          </thead>
          {visibleGroups.map((group) => {
            const groupTrees = visibleTrees.filter(
              (tree) => (tree.group_id ?? defaultGroupId) === group.id,
            );
            const collapsed = collapsedGroupIds.has(group.id);
            return (
              <tbody key={group.id} data-testid={`group-section-${group.id}`}>
                <tr
                  className="tree-group-row"
                  data-testid={`group-row-${group.id}`}
                  onClick={() => toggleGroup(group.id)}
                >
                  <td colSpan={6}>
                    <div className="tree-group-row__content">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="tree-group-row__toggle"
                        data-testid={`group-toggle-${group.id}`}
                        aria-label={collapsed ? "展开分组" : "收起分组"}
                        aria-expanded={!collapsed}
                        onClick={(event) => {
                          event.stopPropagation();
                          toggleGroup(group.id);
                        }}
                      >
                        {collapsed ? "▸" : "▾"}
                      </Button>
                      <strong className="tree-group-row__name">{group.name}</strong>
                      <span className="muted">{groupTrees.length} 棵行为树</span>
                      {group.is_default ? <span className="tree-status tree-status--published">默认</span> : null}
                      <div className="tree-group-row__actions" onClick={(event) => event.stopPropagation()}>
                        <Button
                          variant="ghost"
                          size="sm"
                          data-testid={`group-edit-${group.id}`}
                          onClick={() => setGroupDialog({ mode: "rename", group })}
                        >
                          编辑
                        </Button>
                        <Button
                          variant="danger"
                          size="sm"
                          data-testid={`group-delete-${group.id}`}
                          disabled={group.is_default}
                          onClick={() => void handleDeleteGroup(group)}
                        >
                          删除
                        </Button>
                      </div>
                    </div>
                  </td>
                </tr>
                {collapsed ? null : groupTrees.length === 0 ? (
                  <tr className="tree-group-empty-row">
                    <td colSpan={6}>该分组暂无行为树</td>
                  </tr>
                ) : (
                  groupTrees.map((tree) => (
                    <tr
                      key={tree.id}
                      className="tree-table__row"
                      data-testid={`tree-row-${tree.id}`}
                      onClick={() => navigate(`/editor/${tree.id}`)}
                    >
                      <td>{tree.name}</td>
                      <td className="tree-table__desc">
                        {tree.description?.trim() ? (
                          <HoverTooltip
                            content={tree.description}
                            className="tree-description"
                            dataTestid={`tree-description-${tree.id}`}
                          >
                            {tree.description}
                          </HoverTooltip>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td>
                        <select
                          className="text-field__input tree-table__group-select"
                          value={tree.group_id ?? defaultGroupId ?? ""}
                          data-testid={`tree-group-${tree.id}`}
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) => {
                            event.stopPropagation();
                            void handleMoveGroup(tree, Number(event.target.value));
                          }}
                        >
                          {groups.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.name}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <span
                          className={`tree-status tree-status--${tree.status}`}
                          data-testid={`tree-status-${tree.id}`}
                        >
                          {tree.status === "draft" ? "草稿" : "正式"}
                        </span>
                      </td>
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
                          {tree.status === "published" && canRunDirectly(tree) ? (
                            <Button
                              variant="ghost"
                              onClick={() => handleRunClick(tree)}
                              data-testid={`run-${tree.id}`}
                            >
                              执行
                            </Button>
                          ) : null}
                          <Button
                            variant="ghost"
                            onClick={() => void handleExport(tree)}
                            disabled={exportingId === tree.id}
                            data-testid={`export-${tree.id}`}
                          >
                            {exportingId === tree.id ? "导出中…" : "导出"}
                          </Button>
                          <Button
                            variant="danger"
                            onClick={() => handleDelete(tree)}
                            data-testid={`delete-${tree.id}`}
                          >
                            删除
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            );
          })}
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

      {groupDialog ? (
        <TreeGroupDialog
          title={groupDialog.mode === "create" ? "新建分组" : "编辑分组"}
          initialName={groupDialog.mode === "rename" ? groupDialog.group.name : ""}
          submitLabel={groupDialog.mode === "create" ? "创建" : "保存"}
          onCancel={() => setGroupDialog(null)}
          onSubmit={(name) =>
            groupDialog.mode === "create"
              ? handleCreateGroup(name)
              : handleRenameGroup(groupDialog.group.id, name)
          }
        />
      ) : null}
    </section>
  );
}