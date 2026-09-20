import { useCallback, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { runsApi } from "../../api/runs";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorMessage } from "../../components/ErrorMessage";
import { StatusBadge, type StatusKind } from "../../components/StatusBadge";
import { usePolling } from "../../hooks/usePolling";
import type { RunDetail, RunOut } from "../../types/run";

const ACTIVE = new Set(["pending", "running"]);

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

export function RunListPage() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<RunDetail | null>(null);

  const { data, error: pollError } = usePolling(
    () => runsApi.listRuns(),
    (runs) => runs.every((r) => !ACTIVE.has(r.status)),
  );
  const runs = data ?? [];

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
      if (!window.confirm(`确认删除执行实例 #${run.id}（树「${run.tree_name}」）？`)) {
        return;
      }
      try {
        await runsApi.deleteRun(run.id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "删除失败");
      }
    },
    [],
  );

  const openSnapshot = useCallback(async (run: RunOut) => {
    setError(null);
    try {
      setSnapshot(await runsApi.getRunDetail(run.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载快照失败");
    }
  }, []);

  return (
    <section className="page" data-testid="run-list-page">
      <header className="page-header">
        <h1 className="page-title">行为树执行列表</h1>
      </header>
      {error ? <ErrorMessage message={error} /> : null}
      {pollError ? <ErrorMessage message={`轮询失败：${pollError.message}`} /> : null}

      {runs.length === 0 ? (
        <EmptyState title="还没有执行记录" hint="在行为树管理页点击「执行」开始第一次运行" />
      ) : (
        <table className="tree-table">
          <thead>
            <tr>
              <th>#</th>
              <th>行为树</th>
              <th>状态</th>
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
                  <Link to={`/runs/${run.id}`} data-testid={`run-link-${run.id}`}>
                    {run.tree_name}
                  </Link>
                </td>
                <td>
                  <StatusBadge kind={statusKind(run.status)} />
                </td>
                <td className="run-cell-json">{JSON.stringify(run.inputs ?? {})}</td>
                <td>{run.duration != null ? `${run.duration}s` : "—"}</td>
                <td title={run.tree_content_hash}>{shortHash(run.tree_content_hash)}</td>
                <td>{formatTime(run.created_at)}</td>
                <td>
                  <div className="tree-table__actions">
                    <Button variant="ghost" onClick={() => handleRetry(run)} data-testid={`run-retry-${run.id}`}>
                      重试
                    </Button>
                    <Button variant="ghost" onClick={() => openSnapshot(run)} data-testid={`run-snapshot-${run.id}`}>
                      查看快照
                    </Button>
                    <Button variant="danger" onClick={() => handleDelete(run)} data-testid={`run-delete-${run.id}`}>
                      删除
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {snapshot ? (
        <div className="snapshot-dialog" data-testid="snapshot-dialog">
          <p className="run-dialog__title">实例 #{snapshot.id}「{snapshot.tree_name}」执行快照</p>
          <pre className="snapshot-dialog__content">{snapshot.content_snapshot}</pre>
          <Button variant="ghost" onClick={() => setSnapshot(null)} data-testid="snapshot-close">
            关闭
          </Button>
        </div>
      ) : null}
    </section>
  );
}