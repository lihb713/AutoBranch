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
import { CanvasTree } from "./CanvasTree";
import { NodePalette } from "./NodePalette";
import { BlockListPanel } from "./BlockListPanel";
import { findNodeById, makeNode, parseDocument, parseTree, serializeDocument, serializeTree } from "./model";
import { useBehaviorTree } from "./useBehaviorTree";
import type { BlockDoc } from "./model";

export function TreeEditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const treeId = id ? Number(id) : null;

  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [checkIssues, setCheckIssues] = useState<CheckIssue[] | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // 方案 2 多块文档：全部块 + 当前编辑块名
  const [blocks, setBlocks] = useState<BlockDoc[]>([]);
  const [activeBlock, setActiveBlock] = useState("");

  const { root, loadTree, createAndAddNode, updateNode, setField, removeNode, moveNode } =
    useBehaviorTree();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setCheckIssues(null);
    setName("");
    if (treeId === null) {
      loadTree(null);
      setLoading(false);
      return;
    }
    treesApi
      .getTree(treeId)
      .then((tree) => {
        if (cancelled) return;
        setName(tree.name);
        // 方案 2：多块文档——全部块入编辑器，默认编辑主块；裸树（无 block 前缀）整文档即主块
        const doc = parseDocument(tree.content);
        const loaded = doc.blocks.length > 0 ? doc.blocks : [];
        setBlocks(loaded);
        const mainName = doc.mainBlock || tree.name;
        setActiveBlock(mainName);
        const mainDoc = loaded.find((b) => b.name === mainName);
        if (mainDoc) {
          loadTree(mainDoc.tree);
        } else {
          // 裸树：整文档即主块行为树
          loadTree(parseTree(tree.content));
        }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [treeId]);

  const isBranchRowTarget = useCallback(
    (parentId: string) => {
      const parent = findNodeById(root, parentId);
      return parent?.type === "Branch";
    },
    [root],
  );

  const handleAddChild = useCallback(
    (parentId: string) => {
      if (isBranchRowTarget(parentId)) {
        createAndAddNode(parentId, "branch");
      } else {
        createAndAddNode(parentId, "Step");
      }
    },
    [createAndAddNode, isBranchRowTarget],
  );

  const setFields = useCallback(
    (id: string, fields: { key: string; value: string }[]) => {
      updateNode(id, { fields });
    },
    [updateNode],
  );

  const handleSave = useCallback(async () => {
    setActionError(null);
    setCheckIssues(null);
    if (!root) {
      setActionError("画布为空：请先从左侧面板拖拽节点构建行为树");
      return;
    }
    if (!name.trim()) {
      setActionError("请填写行为树名称");
      return;
    }
    // 把当前编辑块树写回 blocks，再整体序列化（含附属块与各块声明）
    const synced: BlockDoc[] = blocks.map((b) =>
      b.name === activeBlock ? { ...b, tree: root } : b,
    );
    const content =
      synced.length > 0
        ? serializeDocument(synced)
        : serializeTree(root);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [root, name, treeId, navigate]);

  const handleRun = useCallback(async () => {
    if (treeId === null) return;
    setActionError(null);
    try {
      const { run_id } = await runsApi.runTree(treeId);
      navigate(`/runs/${run_id}`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "触发执行失败");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [treeId, navigate]);

  // 把当前编辑树写回 activeBlock（切换/保存前调用）
  const syncActiveTree = useCallback(() => {
    if (!activeBlock || root === null) return;
    setBlocks((prev) => prev.map((b) => (b.name === activeBlock ? { ...b, tree: root } : b)));
  }, [activeBlock, root]);

  const handleSelectBlock = useCallback(
    (blockName: string) => {
      if (blockName === activeBlock) return;
      syncActiveTree();
      setSelectedId(null);
      setActiveBlock(blockName);
      const target = blocks.find((b) => b.name === blockName);
      loadTree(target ? target.tree : null);
    },
    [activeBlock, blocks, loadTree, syncActiveTree],
  );

  const handleCreateBlock = useCallback(() => {
    const existing = new Set(blocks.map((b) => b.name));
    let newName = prompt("新块名称（将作为附属块，可被 this/<块名> 引用）");
    if (!newName) return;
    newName = newName.trim();
    if (!newName || existing.has(newName)) {
      setActionError(`块名无效或已存在: ${newName}`);
      return;
    }
    syncActiveTree();
    setSelectedId(null);
    setBlocks((prev) => [...prev, { name: newName, decl: {}, tree: makeNode("Sequence", [], []) }]);
    setActiveBlock(newName);
    loadTree(makeNode("Sequence", [], []));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blocks, loadTree, syncActiveTree]);

  const handleDeleteBlock = useCallback(
    (blockName: string) => {
      if (blockName === name.trim()) {
        setActionError("主块（行为树名）不可删除");
        return;
      }
      if (blockName === activeBlock) {
        syncActiveTree();
        const next = blocks.filter((b) => b.name !== blockName);
        setBlocks(next);
        const main = next.find((b) => b.name === name.trim());
        setActiveBlock(main ? main.name : "");
        loadTree(main ? main.tree : null);
      } else {
        setBlocks((prev) => prev.filter((b) => b.name !== blockName));
      }
    },
    [activeBlock, blocks, loadTree, name, syncActiveTree],
  );

  const treeName = useMemo(() => name.trim() || "未命名行为树", [name]);

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
        <h1 className="page-title">{treeId === null ? "新建行为树" : `编辑：${treeName}`}</h1>
        <div className="page-actions">
          <Button variant="ghost" onClick={() => navigate("/")}>
            返回列表
          </Button>
          <Button variant="ghost" onClick={handleRun} disabled={treeId === null || saving}>
            执行
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </Button>
        </div>
      </header>

      {actionError ? <ErrorMessage message={actionError} /> : null}
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

      <div className="editor">
        <BlockListPanel
          blocks={blocks}
          mainBlock={name.trim() || blocks[0]?.name || ""}
          activeBlock={activeBlock}
          onSelect={handleSelectBlock}
          onCreate={handleCreateBlock}
          onDelete={handleDeleteBlock}
        />
        <NodePalette />
        <div className="editor__main">
          <div className="editor__toolbar">
            <TextField
              label="行为树名称"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如：登录流程"
            />
            {treeId !== null ? (
              <span className="canvas__drop-hint">保存前将先执行清晰度校验（/check）</span>
            ) : (
              <span className="canvas__drop-hint">新建保存时由后端校验文档清晰度</span>
            )}
          </div>
          <CanvasTree
            root={root}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onSetField={setField}
            onSetFields={setFields}
            onRemove={removeNode}
            onMove={moveNode}
            onDropNode={createAndAddNode}
            onAddChild={handleAddChild}
          />
          {root === null ? (
            <EmptyState title="还没有节点" hint="拖拽左侧面板的节点到画布开始构建" />
          ) : null}
        </div>
      </div>
    </section>
  );
}