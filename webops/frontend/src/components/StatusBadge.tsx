export type StatusKind = "success" | "failure" | "running";

const LABELS: Record<StatusKind, string> = {
  success: "SUCCESS",
  failure: "FAILURE",
  running: "RUNNING",
};

export function StatusBadge({ kind }: { kind: StatusKind }) {
  return <span className={`status-badge status-${kind}`}>{LABELS[kind]}</span>;
}