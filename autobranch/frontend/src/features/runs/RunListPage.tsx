import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { runsApi } from "../../api/runs";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorMessage } from "../../components/ErrorMessage";
import { StatusBadge, type StatusKind } from "../../components/StatusBadge";
import type { RunOut } from "../../types/run";

function statusKind(status: string): StatusKind {
  if (status === "success") return "success";
  if (status === "failure") return "failure";
  if (status === "pending") return "pending";
  return "running";
}

function formatTime(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("zh-CN");
}

function shortHash(hash: string): string {
  return hash ? `#${hash.slice(0, 7)}` : "—";
}

function sourceLabel(source: string): string {
  if (source === "schedule") return "调度";
  if (source === "dependency") return "依赖";
  return "手动";
}

function sourceTone(source: string): "primary" | "warning" | "neutral" {
  if (source === "schedule") return "primary";
  if (source === "dependency") return "warning";
  return "neutral";
}

const POLL_MS = 2000;

export function RunListPage() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<RunOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await runsApi.listRuns();
      setRuns(list);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载执行列表失败");
    } finally {
      setLoading(false);
    }
  }, []);

  // 挂载加载 + 周期刷新（调度可能在页面停留期间自动触发新实例）
  useEffect(() => {
    let cancelled = false;
    void load();

    const tick = async () => {
      if (cancelled) return;
      const list = await runsApi.listRuns().catch(() => null);
      if (cancelled || list === null) return;
      setRuns(list);
      pollRef.current = setTimeout(tick, POLL_MS);
    };
    pollRef.current = setTimeout(tick, POLL_MS);
    return () => {
      cancelled = true;
      if (pollRef.current !== null) clearTimeout(pollRef.current);
    };
  }, [load]);

  const handleRetry = useCallback(
    async (run: RunOut) => {
      setError(null);
      try {
        const { run_id } = await runsApi.retryRun(run.id);
        navigate(`/runs/${run_id}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "重试失败");
      }
    },
    [navigate],
  );

  const handleDelete = useCallback(
    async (run: RunOut) => {
      setError(null);
      try {
        await runsApi.deleteRun(run.id);
        // 立即刷新，避免残留已删除记录
        setRuns((prev) => prev.filter((r) => r.id !== run.id));
        void load();
      } catch (e) {
        setError(e instanceof Error ? e.message : "删除失败");
      }
    },
    [load],
  );

  return (
    <section className="page" data-testid="run-list-page">
      <header className="page-header">
        <h1 className="page-title">行为树执行列表</h1>
      </header>
      {error ? <ErrorMessage message={error} /> : null}

      {loading && runs.length === 0 ? (
        <div className="page-loading">加载中…</div>
      ) : runs.length === 0 ? (
        <EmptyState title="还没有执行记录" hint="在行为树管理页点击「执行」开始第一次运行" />
      ) : (
        <table className="tree-table">
          <thead>
            <tr>
              <th>#</th>
              <th>行为树</th>
              <th>状态</th>
              <th>来源</th>
              <th>入参</th>
              <th>耗时</th>
              <th>指纹</th>
              <th>开始时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="tree-table__row" data-testid={`run-row-${run.id}`}>
                <td>{run.id}</td>
                <td>
                  <button
                    className="link"
                    onClick={() => navigate(`/runs/${run.id}`)}
                    data-testid={`run-link-${run.id}`}
                  >
                    {run.tree_name}
                  </button>
                </td>
                <td>
                  <StatusBadge kind={statusKind(run.status)} />
                </td>
                <td>
                  <Badge
                    tone={sourceTone(run.source || "manual")}
                    className={`source-${run.source || "manual"}`}
                    data-testid={`run-source-${run.id}`}
                  >
                    {sourceLabel(run.source || "manual")}
                  </Badge>
                </td>
                <td className="run-cell-json">{JSON.stringify(run.inputs ?? {})}</td>
                <td>{run.duration != null ? `${run.duration}s` : "—"}</td>
                <td title={run.tree_content_hash}>{shortHash(run.tree_content_hash)}</td>
                <td>{formatTime(run.created_at)}</td>
                <td>
                  <div className="tree-table__actions">
                    <Button
                      variant="ghost"
                      onClick={() => navigate(`/runs/${run.id}`)}
                      data-testid={`run-view-${run.id}`}
                    >
                      查看
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => handleRetry(run)}
                      data-testid={`run-retry-${run.id}`}
                    >
                      重试
                    </Button>
                    <Button
                      variant="danger"
                      onClick={() => handleDelete(run)}
                      data-testid={`run-delete-${run.id}`}
                    >
                      删除
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}