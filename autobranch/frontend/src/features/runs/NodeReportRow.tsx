import { runsApi } from "../../api/runs";
import { Screenshot } from "../../components/Screenshot";
import { StatusBadge, type StatusKind } from "../../components/StatusBadge";
import type { NodeReport } from "../../types/run";

function statusKind(result: string): StatusKind {
  if (result === "success") return "success";
  if (result === "failure") return "failure";
  return "running";
}

export function NodeReportRow({ report }: { report: NodeReport }) {
  const kind = statusKind(report.result);
  const shotPath = report.screenshot_path;

  return (
    <div
      className={`report-node node-${kind}`}
      data-testid={`report-node-${report.node_type}`}
      data-result={report.result}
    >
      <div className="report-node__header">
        <StatusBadge kind={kind} />
        <span className="report-node__type">{report.node_type}</span>
        {report.node_desc ? <span className="report-node__desc">{report.node_desc}</span> : null}
      </div>
      <div className="report-node__meta">
        <span>{report.timestamp}</span>
        {report.condition_result !== null ? (
          <span> · 条件结果: {String(report.condition_result)}</span>
        ) : null}
        {report.action_call ? (
          <span> · 调用: {report.action_call.function}</span>
        ) : null}
        {report.page_url ? <span> · URL: {report.page_url}</span> : null}
      </div>
      {shotPath ? (
        <Screenshot src={runsApi.getReportFile(shotPath)} alt={`${report.node_type} 截图`} />
      ) : null}
    </div>
  );
}