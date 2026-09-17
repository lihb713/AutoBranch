import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { pluginsApi } from "../../api/plugins";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorMessage } from "../../components/ErrorMessage";
import type { PluginOut } from "../../types/plugin";

export function PluginListPage() {
  const [plugins, setPlugins] = useState<PluginOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    pluginsApi
      .listPlugins()
      .then(setPlugins)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleDelete = async (plugin: PluginOut) => {
    const refs = await pluginsApi.listReferences(plugin.name).catch(() => []);
    const message =
      refs.length > 0
        ? `插件「${plugin.name}」被行为树 ${refs.join("、")} 引用，删除后其 FunctionCall 引用将被置空。确认删除？`
        : `确认删除插件「${plugin.name}」？`;
    if (!window.confirm(message)) {
      return;
    }
    await pluginsApi.deletePlugin(plugin.name);
    setPlugins((prev) => prev.filter((p) => p.name !== plugin.name));
  };

  return (
    <div className="page">
      <header className="page-header">
        <h1>插件管理</h1>
        <Link to="/plugins/new">
          <Button>新增插件</Button>
        </Link>
      </header>
      {error && <ErrorMessage message={error} />}
      {!loading && plugins.length === 0 && <EmptyState title="暂无插件" />}
      {plugins.length > 0 && (
        <table className="tree-table">
          <thead>
            <tr>
              <th>插件</th>
              <th>来源</th>
              <th>描述</th>
              <th>函数</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {plugins.map((p) => (
              <tr key={p.name}>
                <td>{p.name}</td>
                <td>
                  <span className={`badge badge-${p.kind}`}>
                    {p.kind === "builtin" ? "预置" : "自定义"}
                  </span>
                </td>
                <td>{p.description}</td>
                <td>{p.functions.join(", ")}</td>
                <td>
                  {p.kind === "custom" ? (
                    <span className="actions">
                      <Link to={`/plugins/edit/${encodeURIComponent(p.name)}`}>编辑</Link>
                      <button className="link" onClick={() => handleDelete(p)}>
                        删除
                      </button>
                    </span>
                  ) : (
                    <span className="actions">
                      <Link to={`/plugins/edit/${encodeURIComponent(p.name)}`}>查看源码</Link>
                      <span className="muted">只读</span>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p>
        <Link to="/">← 返回行为树</Link>
      </p>
    </div>
  );
}