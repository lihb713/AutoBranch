import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/request";
import { runsApi } from "../../api/runs";
import { treesApi } from "../../api/trees";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorMessage } from "../../components/ErrorMessage";
import { TextField } from "../../components/TextField";
import type { CheckIssue } from "../../types/check";
import { NodePalette } from "./NodePalette";
import { DocInterfaceEditor } from "./DocInterfaceEditor";
import { PropertyPanel } from "./PropertyPanel";
import { TreeCanvas } from "./TreeCanvas";
import { parseDoc, type NodeType, type TreeDoc } from "./treeModel";
import type { TreeCommand, TreeDetailOut, TreeStatus } from "../../types/tree";
import { validateDoc, type RefMeta } from "./validation";

function collectRefTargets(doc: TreeDoc): string[] {
  const targets: string[] = [];
  for (const n of Object.values(doc.nodes)) {
    if (n.type === "ref" && n.target && n.target.trim()) targets.push(n.target.trim());
  }
  return targets;
}

export function TreeEditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const treeId = id ? Number(id) : null;

  const [doc, setDoc] = useState<TreeDoc | null>(null);
  const [name, setName] = useState("");
  const [status, setStatus] = useState<TreeStatus>("draft");
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [checkIssues, setCheckIssues] = useState<CheckIssue[] | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedPreview, setSelectedPreview] = useState<{ refId: string; nodeId: string } | null>(null);
  const [docNames, setDocNames] = useState<string[]>([]);
  const [refMeta, setRefMeta] = useState<Record<string, RefMeta>>({});
  const [docRefs, setDocRefs] = useState<Record<string, string[]>>({});
  const [expandedRefs, setExpandedRefs] = useState<Set<string>>(new Set());
  const [refPreviews, setRefPreviews] = useState<Record<string, TreeDoc>>({});
  const [activeTab, setActiveTab] = useState<"property" | "nodes" | "tree">("property");
  const refMetaLoading = useRef<Set<string>>(new Set());
  const refMetaFailed = useRef<Set<string>>(new Set());
  const draftRequested = useRef(false);
  const pendingPatches = useRef<Map<string, Record<string, unknown>>>(new Map());
  const patchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 加载全部文档名（ref 目标下拉）
  useEffect(() => {
    treesApi
      .listTrees(true)
      .then((list) => setDocNames(list.map((t) => t.name)))
      .catch(() => setDocNames([]));
  }, []);

  const applyDetail = useCallback((tree: TreeDetailOut) => {
    setDoc(parseDoc(tree.content));
    setName(tree.name);
    setStatus(tree.status);
  }, []);

  const runCommands = useCallback(
    async (commands: TreeCommand[]) => {
      if (treeId === null) return null;
      setActionError(null);
      try {
        const result = await treesApi.applyCommands(treeId, commands);
        applyDetail(result.tree);
        return result.created_node_id;
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "编辑失败");
        return null;
      }
    },
    [applyDetail, treeId],
  );

  const flushPendingPatches = useCallback(async () => {
    if (patchTimer.current) {
      clearTimeout(patchTimer.current);
      patchTimer.current = null;
    }
    const entries = Array.from(pendingPatches.current.entries());
    pendingPatches.current.clear();
    if (entries.length === 0) return;
    await runCommands(
      entries.map(([nodeId, patch]) => ({ op: "update_node", node_id: nodeId, patch })),
    );
  }, [runCommands]);

  const schedulePatch = useCallback(
    (nodeId: string, patch: Record<string, unknown>) => {
      const merged = { ...(pendingPatches.current.get(nodeId) ?? {}), ...patch };
      pendingPatches.current.set(nodeId, merged);
      if (patchTimer.current) clearTimeout(patchTimer.current);
      patchTimer.current = setTimeout(() => {
        void flushPendingPatches();
      }, 250);
    },
    [flushPendingPatches],
  );

  // 加载当前文档；/editor 无 id 时立即创建草稿并跳转
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setCheckIssues(null);
    setName("");
    setSelectedId(null);
    setRefMeta({});
    setDocRefs({});
    if (treeId === null) {
      if (draftRequested.current) return;
      draftRequested.current = true;
      treesApi
        .createDraft()
        .then((tree) => {
          if (cancelled) return;
          navigate(`/editor/${tree.id}`, { replace: true });
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setLoadError(err instanceof Error ? err.message : "创建草稿失败");
          setLoading(false);
        });
      return () => {
        cancelled = true;
      };
    }
    draftRequested.current = false;
    treesApi
      .getTree(treeId)
      .then((tree) => {
        if (cancelled) return;
        applyDetail(tree);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applyDetail, navigate, treeId]);

  const loadRefMeta = useCallback((target: string) => {
    if (refMeta[target] || refMetaLoading.current.has(target) || refMetaFailed.current.has(target)) {
      return;
    }
    refMetaLoading.current.add(target);
    treesApi
      .getTreeByName(target)
      .then((tree) => {
        try {
          const targetDoc = parseDoc(tree.content);
          setRefMeta((prev) => ({
            ...prev,
            [target]: {
              inputs: targetDoc.inputs,
              outputs: targetDoc.outputs,
            },
          }));
          setDocRefs((prev) => ({ ...prev, [target]: collectRefTargets(targetDoc) }));
        } catch {
          refMetaFailed.current.add(target);
        }
      })
      .catch(() => {
        refMetaFailed.current.add(target);
      })
      .finally(() => {
        refMetaLoading.current.delete(target);
      });
  }, [refMeta]);

  // 加载文档/新增 ref 目标后，自动加载全部 ref 目标的 inputs/outputs（幂等，仅缺失时请求）
  useEffect(() => {
    if (!doc) return;
    for (const n of Object.values(doc.nodes)) {
      if (n.type === "ref" && n.target) loadRefMeta(n.target);
    }
  }, [doc, loadRefMeta]);

  const refTargetsOf = useCallback(
    (docName: string) => {
      if (docName === (doc?.tree ?? "")) {
        return doc ? collectRefTargets(doc) : [];
      }
      return docRefs[docName] ?? [];
    },
    [doc, docRefs],
  );

  const toggleRef = useCallback(
    (refId: string) => {
      if (!doc) return;
      if (expandedRefs.has(refId)) {
        // 收缩：移除展开标记并清除预览（TreeCanvas 布局/渲染基于 refPreviews）
        const next = new Set(expandedRefs);
        next.delete(refId);
        setExpandedRefs(next);
        setRefPreviews((prev) => {
          if (!(refId in prev)) return prev;
          const copy = { ...prev };
          delete copy[refId];
          return copy;
        });
        setSelectedPreview((prev) => (prev && prev.refId === refId ? null : prev));
        return;
      }
      const refNode = doc.nodes[refId];
      if (!refNode || refNode.type !== "ref" || !refNode.target) return;
      loadRefMeta(refNode.target);
      treesApi
        .getTreeByName(refNode.target)
        .then((tree) => {
          try {
            setRefPreviews((prev) => ({ ...prev, [refId]: parseDoc(tree.content) }));
            setExpandedRefs((prev) => new Set(prev).add(refId));
          } catch {
            // 被引文档解析失败：保持收缩
          }
        })
        .catch(() => {
          // 目标不存在：保持收缩
        });
    },
    [doc, expandedRefs, loadRefMeta],
  );

  // 即时校验
  const { issues, issueByNode } = useMemo(() => {
    if (!doc) return { issues: [], issueByNode: new Map<string, Set<string>>() };
    const found = validateDoc(doc, { docNames, refMeta, refTargetsOf });
    const byNode = new Map<string, Set<string>>();
    for (const issue of found) {
      if (!issue.nodeId) continue;
      const set = byNode.get(issue.nodeId) ?? new Set<string>();
      if (issue.field) set.add(issue.field);
      byNode.set(issue.nodeId, set);
    }
    return { issues: found, issueByNode: byNode };
  }, [doc, docNames, refMeta, refTargetsOf]);

  const handleAddNode = useCallback(
    async (type: NodeType) => {
      setActiveTab("property");
      await flushPendingPatches();
      const created = await runCommands([{ op: "add_node", node_type: type }]);
      if (created) setSelectedId(created);
    },
    [flushPendingPatches, runCommands],
  );

  const handleDeleteNode = useCallback(
    async (nodeId: string, subtree: boolean) => {
      await flushPendingPatches();
      const result = await runCommands([{ op: "delete_node", node_id: nodeId, subtree }]);
      if (result !== null && selectedId === nodeId) setSelectedId(null);
    },
    [flushPendingPatches, runCommands, selectedId],
  );

  const handlePatchNode = useCallback(
    (nodeId: string, patch: Partial<Record<string, unknown>>) => {
      schedulePatch(nodeId, patch as Record<string, unknown>);
    },
    [schedulePatch],
  );

  const handleSlotChange = useCallback(
    async (nodeId: string, slotIndex: number, childId: string | null) => {
      await flushPendingPatches();
      await runCommands([
        childId
          ? { op: "set_slot", node_id: nodeId, slot_index: slotIndex, child_id: childId }
          : { op: "detach_slot", node_id: nodeId, slot_index: slotIndex },
      ]);
    },
    [flushPendingPatches, runCommands],
  );

  const handlePatchDoc = useCallback(
    async (patch: Partial<TreeDoc>) => {
      const payload: Record<string, unknown> = {};
      if (patch.inputs !== undefined) payload.inputs = patch.inputs;
      if (patch.outputs !== undefined) payload.outputs = patch.outputs;
      if (patch.config !== undefined) payload.config = patch.config;
      if (patch.tree !== undefined) payload.tree = patch.tree;
      await flushPendingPatches();
      await runCommands([{ op: "update_doc", patch: payload }]);
    },
    [flushPendingPatches, runCommands],
  );

  const handleSave = useCallback(async () => {
    setActionError(null);
    setCheckIssues(null);
    if (!doc || treeId === null) return;
    if (!name.trim()) {
      setActionError("请填写行为树名称");
      return;
    }
    setSaving(true);
    try {
      await flushPendingPatches();
      const detail = await treesApi.saveTree(treeId, name.trim());
      applyDetail(detail);
      navigate("/");
    } catch (err) {
      if (err instanceof ApiError) {
        if (Array.isArray(err.detail)) {
          setCheckIssues(err.detail as CheckIssue[]);
        } else {
          setActionError(err.message);
        }
      } else {
        setActionError(err instanceof Error ? err.message : "保存失败");
      }
    } finally {
      setSaving(false);
    }
  }, [applyDetail, doc, flushPendingPatches, name, navigate, treeId]);

  const handleRun = useCallback(async () => {
    if (treeId === null) return;
    setActionError(null);
    try {
      const { run_id } = await runsApi.runTree(treeId);
      navigate(`/runs/${run_id}`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "触发执行失败");
    }
  }, [treeId, navigate]);

  useEffect(
    () => () => {
      if (patchTimer.current) clearTimeout(patchTimer.current);
    },
    [],
  );

  const handleSelect = useCallback((id: string) => {
    setSelectedId(id);
    setSelectedPreview(null);
    setActiveTab("property");
  }, []);

  const handleSelectPreview = useCallback((refId: string, nodeId: string) => {
    setSelectedPreview({ refId, nodeId });
  }, []);

  const previewNode =
    selectedPreview && refPreviews[selectedPreview.refId]
      ? (refPreviews[selectedPreview.refId].nodes[selectedPreview.nodeId] ?? null)
      : null;
  const selectedNode =
    previewNode ?? (doc && selectedId ? (doc.nodes[selectedId] ?? null) : null);
  const selectedDoc =
    selectedPreview && refPreviews[selectedPreview.refId] ? refPreviews[selectedPreview.refId] : doc;

  if (loading) {
    return <div className="page-loading">加载中…</div>;
  }

  if (loadError) {
    return (
      <div className="page-error">
        <ErrorMessage message={loadError} />
        <Button variant="ghost" onClick={() => navigate("/")}>
          返回列表
        </Button>
      </div>
    );
  }

  return (
    <section className="editor-page">
      <header className="page-header">
        <h1 className="page-title">{treeId === null ? "新建行为树" : `编辑：${name || "未命名行为树"}`}</h1>
        <div className="page-actions">
          <Button variant="ghost" onClick={() => navigate("/")}>
            返回列表
          </Button>
          <Button
            variant="ghost"
            onClick={handleRun}
            disabled={treeId === null || saving || status !== "published"}
            title={status === "draft" ? "草稿需保存为正式版后才能执行" : undefined}
          >
            执行
          </Button>
          <Button onClick={handleSave} disabled={saving || !doc}>
            {saving ? "保存中…" : "保存"}
          </Button>
        </div>
      </header>

      {actionError ? <ErrorMessage message={actionError} /> : null}
      {issues.length > 0 ? (
        <div className="error-message" role="alert" data-testid="local-issues">
          <p>即时校验（{issues.length} 项）：</p>
          <ul>
            {issues.slice(0, 8).map((issue, i) => (
              <li key={i} data-testid={`local-issue-${i}`}>
                {issue.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {checkIssues && checkIssues.length > 0 ? (
        <div className="error-message" role="alert" data-testid="check-issues">
          <p>清晰度校验未通过，请修正后重新保存：</p>
          <ul>
            {checkIssues.map((issue, i) => (
              <li key={i} data-testid={`issue-${i}`}>
                {issue.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {doc ? (
        <div className="editor">
          <div className="editor__main">
            <TreeCanvas
              doc={doc}
              selectedId={selectedId}
              issueByNode={issueByNode}
              refPreviews={refPreviews}
              onToggleRef={toggleRef}
              onSelect={handleSelect}
              onSelectPreview={handleSelectPreview}
            />
            {Object.keys(doc.nodes).length <= 1 ? (
              <EmptyState title="还没有节点" hint="点击右侧「节点」面板添加" />
            ) : null}
          </div>
          <aside className="editor__side" data-testid="editor-side">
            <div className="editor__side-tabs" role="tablist" aria-label="侧栏面板">
              <button
                type="button"
                className={`editor__side-tab${activeTab === "property" ? " editor__side-tab--active" : ""}`}
                data-testid="side-tab-property"
                onClick={() => setActiveTab("property")}
              >
                属性
              </button>
              <button
                type="button"
                className={`editor__side-tab${activeTab === "nodes" ? " editor__side-tab--active" : ""}`}
                data-testid="side-tab-nodes"
                onClick={() => setActiveTab("nodes")}
              >
                节点
              </button>
              <button
                type="button"
                className={`editor__side-tab${activeTab === "tree" ? " editor__side-tab--active" : ""}`}
                data-testid="side-tab-tree"
                onClick={() => setActiveTab("tree")}
              >
                树信息
              </button>
            </div>
            <div className="editor__side-body">
              {activeTab === "property" ? (
                <PropertyPanel
                  doc={selectedDoc ?? doc}
                  node={selectedNode}
                  readonly={selectedPreview !== null}
                  docNames={docNames}
                  refMeta={refMeta}
                  refTargetsOf={refTargetsOf}
                  onPatchNode={handlePatchNode}
                  onSlotChange={handleSlotChange}
                  onLoadRefMeta={loadRefMeta}
                  onDeleteNode={handleDeleteNode}
                />
              ) : null}
              {activeTab === "nodes" ? (
                <NodePalette onAdd={handleAddNode} />
              ) : null}
              {activeTab === "tree" ? (
                <div className="editor__side-tree" data-testid="side-tab-tree-content">
                  <TextField
                    label="行为树名称"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="如：登录流程"
                  />
                  <DocInterfaceEditor
                    doc={doc}
                    readonly={selectedPreview !== null}
                    onPatch={(patch) => void handlePatchDoc(patch)}
                  />
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      ) : null}
    </section>
  );
}