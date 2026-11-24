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
        {report.node_id ? <span className="report-node__id">#{report.node_id}</span> : null}
        {report.node_desc ? <span className="report-node__desc">{report.node_desc}</span> : null}
      </div>
      <div className="report-node__meta">
        <span>{report.timestamp}</span>
        {report.duration != null ? <span> · 耗时: {report.duration}s</span> : null}
        {report.condition_result !== null ? (
          <span> · 条件结果: {String(report.condition_result)}</span>
        ) : null}
        {report.action_call ? (
          <span> · 调用: {report.action_call.function}</span>
        ) : null}
        {report.parallel ? <span> · 并行: {report.parallel}</span> : null}
        {report.function ? <span> · 函数: {report.function}</span> : null}
        {report.page_url ? <span> · URL: {report.page_url}</span> : null}
      </div>
      {report.arguments || report.kwargs || report.returns || report.details ? (
        <div className="report-node__io">
          {report.arguments ? <div>入参: {JSON.stringify(report.arguments)}</div> : null}
          {report.kwargs ? <div>命名参数: {JSON.stringify(report.kwargs)}</div> : null}
          {report.returns ? <div>出参: {JSON.stringify(report.returns)}</div> : null}
          {report.details ? <div>详情: {JSON.stringify(report.details)}</div> : null}
        </div>
      ) : null}
      {report.failure_reason ? (
        <div className="report-node__failure" data-testid="node-failure-reason">
          {report.failure_reason}
        </div>
      ) : null}
      {shotPath ? (
        <Screenshot src={runsApi.getReportFile(shotPath)} alt={`${report.node_type} 截图`} />
      ) : null}
    </div>
  );
}