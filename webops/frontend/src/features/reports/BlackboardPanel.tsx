import type { BlackboardVar } from "../../types/run";

type BlackboardPanelProps = {
  variables: BlackboardVar[];
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

export function BlackboardPanel({ variables }: BlackboardPanelProps) {
  return (
    <section className="blackboard-panel" data-testid="blackboard-panel" aria-label="变量黑板">
      <h2 className="blackboard-panel__title">变量黑板</h2>
      {variables.length === 0 ? (
        <p className="blackboard-panel__empty">（暂无变量）</p>
      ) : (
        <table className="blackboard-panel__table">
          <thead>
            <tr>
              <th>变量</th>
              <th>类型</th>
              <th>值</th>
            </tr>
          </thead>
          <tbody>
            {variables.map((item) => (
              <tr key={item.path} data-testid={`blackboard-var-${item.path}`}>
                <td className="blackboard-panel__path">{item.path}</td>
                <td>{item.type || "—"}</td>
                <td className="blackboard-panel__value">{formatValue(item.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}