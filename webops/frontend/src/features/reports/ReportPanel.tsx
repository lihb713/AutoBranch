import { useState } from "react";
import { Button } from "../../components/Button";
import { ErrorMessage } from "../../components/ErrorMessage";

type ReportPanelProps = {
  execText: string | null;
  traceText: string | null;
  error?: string | null;
};

export function ReportPanel({ execText, traceText, error }: ReportPanelProps) {
  const [view, setView] = useState<"report" | "trace">("report");

  const text = view === "report" ? execText : traceText;

  return (
    <section className="report-panel" data-testid="report-panel">
      <div className="report-panel__tabs" role="tablist">
        <Button
          variant={view === "report" ? "primary" : "ghost"}
          className={`report-panel__tab${view === "report" ? " report-panel__tab--active" : ""}`}
          onClick={() => setView("report")}
        >
          完整执行报告
        </Button>
        <Button
          variant={view === "trace" ? "primary" : "ghost"}
          className={`report-panel__tab${view === "trace" ? " report-panel__tab--active" : ""}`}
          onClick={() => setView("trace")}
        >
          回溯报告
        </Button>
      </div>
      {error ? <ErrorMessage message={error} /> : null}
      {text === null ? (
        <p className="report-panel__text">报告加载中…</p>
      ) : text.length === 0 ? (
        <p className="report-panel__text">（报告为空）</p>
      ) : (
        <pre className="report-panel__text">{text}</pre>
      )}
    </section>
  );
}