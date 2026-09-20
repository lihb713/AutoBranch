export type StatusKind = "success" | "failure" | "running" | "pending";

const LABELS: Record<StatusKind, string> = {
  success: "SUCCESS",
  failure: "FAILURE",
  running: "RUNNING",
  pending: "排队中",
};

export function StatusBadge({ kind }: { kind: StatusKind }) {
  return <span className={`status-badge status-${kind}`}>{LABELS[kind]}</span>;
}