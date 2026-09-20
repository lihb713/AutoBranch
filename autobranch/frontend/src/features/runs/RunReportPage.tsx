import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { runsApi } from "../../api/runs";
import { Button } from "../../components/Button";
import { ErrorMessage } from "../../components/ErrorMessage";
import { StatusBadge } from "../../components/StatusBadge";
import { usePolling } from "../../hooks/usePolling";
import type { RunDetail } from "../../types/run";
import { BlackboardPanel } from "../reports/BlackboardPanel";
import { ReportPanel } from "../reports/ReportPanel";
import { NodeReportRow } from "./NodeReportRow";

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

  const finished = data?.finished === true;

  useEffect(() => {
    if (!finished || runId === undefined) return;
    let cancelled = false;
    setReportError(null);
    runsApi
      .getRunDetail(runId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch(() => undefined);
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

  const statusKind = data?.failure_reason ? "failure" : finished ? "success" : "running";

  return (
    <section className="run-report-page">
      <header className="page-header">
        <h1 className="page-title">执行报告 #{runId}</h1>
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
      {data?.failure_reason ? (
        <ErrorMessage message={`执行失败：${data.failure_reason}`} />
      ) : null}

      {data === null && error === null ? <div className="page-loading">等待执行状态…</div> : null}

      {detail?.outputs && Object.keys(detail.outputs).length > 0 ? (
        <div className="outputs-section" data-testid="outputs-section">
          <h2 className="outputs-section__title">出参</h2>
          <pre className="outputs-section__body">{JSON.stringify(detail.outputs, null, 2)}</pre>
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