import type { FunctionInfo } from "../../types/plugin";

function paramRows(fn: FunctionInfo): { name: string; type: string; required: boolean; description: string }[] {
  const params = (fn.parameters ?? {}) as {
    properties?: Record<string, { type?: string; description?: string }>;
    required?: string[];
  };
  const required = new Set(params.required ?? []);
  return Object.entries(params.properties ?? {}).map(([name, spec]) => ({
    name,
    type: spec.type ?? "any",
    required: required.has(name),
    description: spec.description ?? "",
  }));
}

export function PluginFunctionDetail({ functions }: { functions: FunctionInfo[] }) {
  if (functions.length === 0) {
    return <p className="muted">该插件暂无函数</p>;
  }
  return (
    <div className="plugin-functions" data-testid="plugin-functions">
      {functions.map((fn) => (
        <section className="plugin-function-card" key={fn.full_name}>
          <div className="plugin-card-header">
            <strong>{fn.full_name}</strong>
            <span className={`badge ${fn.user_visible === false ? "badge-custom" : "badge-builtin"}`}>
              {fn.user_visible === false ? "仅 LLM" : "用户可见"}
            </span>
            {fn.output_param ? <span className="badge badge-builtin">产出型</span> : null}
          </div>
          <p className="plugin-desc">{fn.description}</p>
          <div className="plugin-function-section">
            <span className="plugin-function-label">入参</span>
            {paramRows(fn).length === 0 ? (
              <span className="muted">（无）</span>
            ) : (
              <ul>
                {paramRows(fn).map((p) => (
                  <li key={p.name}>
                    <code>{p.name}</code> ({p.type}{p.required ? ", 必填" : ""})
                    {p.description ? ` — ${p.description}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="plugin-function-section">
            <span className="plugin-function-label">出参</span>
            {Object.keys(fn.returns ?? {}).length === 0 ? (
              <span className="muted">（无）</span>
            ) : (
              <ul>
                {Object.entries(fn.returns).map(([name, type]) => (
                  <li key={name}>
                    <code>{name}</code> ({type})
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      ))}
    </div>
  );
}
