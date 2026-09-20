import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { runsApi } from "../../api/runs";
import { Button } from "../../components/Button";
import { ErrorMessage } from "../../components/ErrorMessage";
import { StatusBadge, type StatusKind } from "../../components/StatusBadge";
import { usePolling } from "../../hooks/usePolling";
import type { RunDetail } from "../../types/run";
import { BlackboardPanel } from "../reports/BlackboardPanel";
import { ReportPanel } from "../reports/ReportPanel";
import { NodeReportRow } from "./NodeReportRow";

function statusKindOf(status: string | undefined): StatusKind {
  if (status === "success") return "success";
  if (status === "failure") return "failure";
  if (status === "pending") return "pending";
  return "running";
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("zh-CN");
}

export function RunReportPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { data, error } = usePolling(
    () => runsApi.getRunState(runId as string),
    (state) => state.finished,
  );

  const [execText, setExecText] = useState<string | null>(null);
  const [traceText, setTraceText] = useState<string | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const finished = data?.finished === true;

  const loadDetail = useCallback(async (id: string) => {
    try {
      const d = await runsApi.getRunDetail(id);
      setDetail(d);
      setDetailError(null);
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : "加载实例信息失败");
    }
  }, []);

  // 挂载即加载实例信息（状态/入参/指纹等），结束后再刷新一次（出参/终态）
  useEffect(() => {
    if (runId === undefined) return;
    void loadDetail(runId);
  }, [runId, loadDetail]);

  useEffect(() => {
    if (finished && runId !== undefined) {
      void loadDetail(runId);
    }
  }, [finished, runId, loadDetail]);

  useEffect(() => {
    if (!finished || runId === undefined) return;
    let cancelled = false;
    setReportError(null);
    Promise.all([runsApi.getRunReport(runId), runsApi.getRunTrace(runId)])
      .then(([rep, trace]) => {
        if (cancelled) return;
        setExecText(typeof rep === "string" ? rep : null);
        setTraceText(typeof trace === "string" ? trace : null);
        if (typeof rep !== "string" || typeof trace !== "string") {
          setReportError("报告尚未生成完成，请稍后重试");
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setReportError(err instanceof Error ? err.message : "加载报告失败");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [finished, runId]);

  const handleRetry = async () => {
    if (runId === undefined) return;
    try {
      const { run_id } = await runsApi.retryRun(runId);
      navigate(`/runs/${run_id}`);
    } catch (err) {
      setReportError(err instanceof Error ? err.message : "重试失败");
    }
  };

  if (runId === undefined) {
    return (
      <div className="page-error">
        <ErrorMessage message="缺少执行编号（runId）" />
        <Button variant="ghost" onClick={() => navigate("/runs")}>
          返回执行列表
        </Button>
      </div>
    );
  }

  const statusKind = statusKindOf(detail?.status);
  const inputs = detail?.inputs ?? {};
  const outputs = detail?.outputs ?? null;

  return (
    <section className="run-report-page">
      <header className="page-header">
        <h1 className="page-title">执行详情 #{runId}</h1>
        <div className="page-actions">
          <StatusBadge kind={statusKind} />
          {finished ? (
            <Button variant="ghost" onClick={() => void handleRetry()} data-testid="report-retry">
              重试
            </Button>
          ) : null}
          <Button variant="ghost" onClick={() => navigate("/runs")}>
            返回执行列表
          </Button>
        </div>
      </header>

      {error ? <ErrorMessage message={`轮询失败：${error.message}`} /> : null}
      {detailError ? <ErrorMessage message={detailError} /> : null}
      {data?.failure_reason ? (
        <ErrorMessage message={`执行失败：${data.failure_reason}`} />
      ) : null}

      {data === null && error === null ? <div className="page-loading">等待执行状态…</div> : null}

      {/* 实例信息：状态 / 行为树 / 入参 / 出参 / 指纹 / 时间 */}
      {detail ? (
        <div className="run-meta" data-testid="run-meta">
          <div className="run-meta__grid">
            <span className="run-meta__label">行为树</span>
            <span className="run-meta__value">{detail.tree_name}</span>
            <span className="run-meta__label">执行状态</span>
            <span className="run-meta__value">
              <StatusBadge kind={statusKind} />
            </span>
            <span className="run-meta__label">指纹</span>
            <span className="run-meta__value" title={detail.tree_content_hash}>
              #{detail.tree_content_hash.slice(0, 7)}
            </span>
            <span className="run-meta__label">开始时间</span>
            <span className="run-meta__value">{formatTime(detail.created_at)}</span>
            <span className="run-meta__label">耗时</span>
            <span className="run-meta__value">
              {detail.duration != null ? `${detail.duration}s` : "—"}
            </span>
          </div>
          <div className="run-meta__section">
            <h2 className="run-meta__title">入参</h2>
            <pre className="run-meta__body">{JSON.stringify(inputs, null, 2)}</pre>
          </div>
          <div className="run-meta__section">
            <h2 className="run-meta__title">出参</h2>
            {outputs && Object.keys(outputs).length > 0 ? (
              <pre className="run-meta__body" data-testid="outputs-section">
                {JSON.stringify(outputs, null, 2)}
              </pre>
            ) : (
              <span className="muted">—</span>
            )}
          </div>
          <details className="run-meta__section" data-testid="snapshot-section">
            <summary className="run-meta__title">执行快照（触发时刻的行为树内容）</summary>
            <pre className="run-meta__body run-meta__body--snapshot">
              {detail.content_snapshot}
            </pre>
          </details>
        </div>
      ) : null}

      {data !== null ? (
        <div className="run-report__body">
          <div className="progress-bar" aria-label={`进度 ${Math.round(data.progress * 100)}%`}>
            <div
              className="progress-bar__fill"
              style={{ width: `${Math.round(data.progress * 100)}%` }}
            />
          </div>
          <p className="progress-text" data-testid="progress-text">
            进度：{Math.round(data.progress * 100)}%{finished ? " · 执行完成" : ""}
          </p>

          {data.current_node ? (
            <div className="report-node node-running" data-testid="current-node">
              <div className="report-node__header">
                <StatusBadge kind="running" />
                <span className="report-node__type">{data.current_node.node_type}</span>
                <span className="report-node__desc">{data.current_node.node_desc}</span>
              </div>
            </div>
          ) : null}

          {data.completed.length > 0 ? (
            <div className="report-nodes">
              {data.completed.map((report, i) => (
                <NodeReportRow key={`${report.timestamp}-${i}`} report={report} />
              ))}
            </div>
          ) : null}

          {finished ? (
            <ReportPanel execText={execText} traceText={traceText} error={reportError} />
          ) : null}

          {data.variables && data.variables.length > 0 ? (
            <BlackboardPanel variables={data.variables} />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}