import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { pluginsApi } from "../../api/plugins";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorMessage } from "../../components/ErrorMessage";
import type { PluginOut } from "../../types/plugin";
import { PluginConfigDialog } from "./PluginConfigDialog";

export function PluginListPage() {
  const [plugins, setPlugins] = useState<PluginOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [configuring, setConfiguring] = useState<PluginOut | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    pluginsApi
      .listPlugins(true)
      .then(setPlugins)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

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
        <div className="plugin-cards" data-testid="plugin-cards">
          {plugins.map((p) => (
            <section
              className="plugin-card"
              key={p.name}
              data-testid={`plugin-card-${p.name}`}
            >
              <div className="plugin-card-header">
                <span className="plugin-name">{p.name}</span>
                <span className={`badge badge-${p.kind}`}>
                  {p.kind === "builtin" ? "预置" : "自定义"}
                </span>
                <span className="plugin-desc">{p.description}</span>
              </div>
              {(p.custom_types?.length ?? 0) > 0 ? (
                <div
                  className="plugin-custom-types"
                  data-testid={`plugin-types-${p.name}`}
                >
                  <span className="muted">自定义类型：</span>
                  {p.custom_types!.map((t) => (
                    <code key={t.token} title={t.description}>
                      {t.token}
                    </code>
                  ))}
                </div>
              ) : null}
              <div className="plugin-card-actions">
                <Link to={`/plugins/edit/${encodeURIComponent(p.name)}`}>
                  查看函数详情
                </Link>
                {(p.config_schema?.length ?? 0) > 0 ? (
                  <button
                    className="link"
                    type="button"
                    data-testid={`plugin-config-${p.name}`}
                    onClick={() => setConfiguring(p)}
                  >
                    配置
                  </button>
                ) : null}
                {(p.frontend_manifest?.pages ?? []).map((page) => (
                  <Link
                    key={page.route}
                    to={page.route}
                    data-testid={`plugin-page-${p.name}-${page.route}`}
                  >
                    {page.label}
                  </Link>
                ))}
                {p.kind === "custom" ? (
                  <button
                    className="link"
                    onClick={() => handleDelete(p)}
                    data-testid={`plugin-delete-${p.name}`}
                  >
                    删除
                  </button>
                ) : (
                  <span className="muted">只读</span>
                )}
              </div>
            </section>
          ))}
        </div>
      )}
      {configuring && configuring.config_schema ? (
        <PluginConfigDialog
          pluginName={configuring.name}
          schema={configuring.config_schema}
          onClose={() => setConfiguring(null)}
          onSaved={reload}
        />
      ) : null}
      <p>
        <Link to="/">← 返回行为树</Link>
      </p>
    </div>
  );
}
