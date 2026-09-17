import { useCallback, useEffect, useMemo, useState } from "react";
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
import {
  createStepWithAction,
  deleteSubtree,
  makeNode,
  nextNodeId,
  parseDoc,
  removeNode,
  serializeDoc,
  type NodeType,
  type TreeDoc,
} from "./treeModel";
import { validateDoc, type RefMeta } from "./validation";

function newEmptyDoc(name: string): TreeDoc {
  return {
    tree: name,
    inputs: {},
    outputs: [],
    config: {},
    nodes: { n1: { id: "n1", type: "Root", name: "根", fields: {} } },
    root: "n1",
  };
}

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

  // 加载全部文档名（ref 目标下拉）
  useEffect(() => {
    treesApi
      .listTrees()
      .then((list) => setDocNames(list.map((t) => t.name)))
      .catch(() => setDocNames([]));
  }, []);

  // 加载当前文档
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
      setDoc(newEmptyDoc(""));
      setLoading(false);
      return;
    }
    treesApi
      .getTree(treeId)
      .then((tree) => {
        if (cancelled) return;
        setName(tree.name);
        setDoc(parseDoc(tree.content));
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
  }, [treeId]);

  const loadRefMeta = useCallback((target: string) => {
    if (refMeta[target]) return;
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
          // 被引文档解析失败不阻断编辑（保存时后端兜底）
        }
      })
      .catch(() => {
        // 目标不存在：校验层已报 missing_doc
      });
  }, [refMeta]);

  const refTargetsOf = useCallback(
    (docName: string) => {
      if (docName === (doc?.tree ?? "")) return collectRefTargets(doc ?? newEmptyDoc(""));
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
    (type: NodeType) => {
      if (!doc) return;
      setActiveTab("property");
      if (type === "Step") {
        const { doc: next, stepId } = createStepWithAction(doc);
        setDoc(next);
        setSelectedId(stepId);
        return;
      }
      const next = { ...doc };
      const id = nextNodeId(next.nodes);
      next.nodes = { ...next.nodes, [id]: makeNode(type, id, next.nodes) };
      setDoc(next);
      setSelectedId(id);
    },
    [doc],
  );

  const handleDeleteNode = useCallback(
    (nodeId: string, subtree: boolean) => {
      if (!doc) return;
      const next = subtree ? deleteSubtree(doc, nodeId) : removeNode(doc, nodeId);
      if (next === null) {
        setActionError("根节点不可删除");
        return;
      }
      setDoc(next);
      if (selectedId === nodeId) setSelectedId(null);
    },
    [doc, selectedId],
  );

  const handleSave = useCallback(async () => {
    setActionError(null);
    setCheckIssues(null);
    if (!doc) return;
    const finalDoc: TreeDoc = { ...doc, tree: name.trim() };
    // 前端汇总校验（阻塞保存）
    const local = validateDoc(finalDoc, { docNames, refMeta, refTargetsOf });
    if (local.length > 0) {
      setCheckIssues(
        local.map((issue) => ({
          code: issue.code,
          message: issue.message,
          rule: "",
          loc: null,
        })),
      );
      return;
    }
    if (!name.trim()) {
      setActionError("请填写行为树名称");
      return;
    }
    const content = serializeDoc(finalDoc);
    setSaving(true);
    try {
      if (treeId !== null) {
        const report = await treesApi.checkTree(treeId);
        if (!report.ok) {
          setCheckIssues(report.issues);
          return;
        }
        await treesApi.updateTree(treeId, { name: name.trim(), content });
      } else {
        await treesApi.createTree({ name: name.trim(), content });
      }
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
  }, [doc, name, treeId, navigate, docNames, refMeta, refTargetsOf]);

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
          <Button variant="ghost" onClick={handleRun} disabled={treeId === null || saving}>
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
                  onUpdate={setDoc}
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
                  <DocInterfaceEditor doc={doc} readonly={selectedPreview !== null} onUpdate={setDoc} />
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      ) : null}
    </section>
  );
}