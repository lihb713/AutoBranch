import { python } from "@codemirror/lang-python";
import CodeMirror from "@uiw/react-codemirror";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { pluginsApi } from "../../api/plugins";
import { ApiError } from "../../api/request";
import { Button } from "../../components/Button";
import { ErrorMessage } from "../../components/ErrorMessage";
import { TextField } from "../../components/TextField";
import type { PluginCheckError } from "../../types/plugin";

const DEFAULT_SOURCE = `class MyPlugin(PluginBase):
    name = "my_plugin"
    description = "我的自定义插件（仅标准库）"

    @engine_function(name="hello", description="返回问候语")
    def hello(self, who="world"):
        return f"hello {who}"

plugin = MyPlugin()
`;

export function PluginEditorPage() {
  const { name } = useParams();
  const isNew = name === "new" || !name;
  const [pluginName, setPluginName] = useState(isNew ? "" : decodeURIComponent(name));
  const [source, setSource] = useState(DEFAULT_SOURCE);
  const [errors, setErrors] = useState<PluginCheckError[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(!isNew);
  const [isBuiltin, setIsBuiltin] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (isNew) {
      return;
    }
    pluginsApi
      .getPlugin(decodeURIComponent(name))
      .then((p) => {
        setPluginName(p.name);
        setSource(p.source ?? "");
        setIsBuiltin(p.kind === "builtin");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [isNew, name]);

  const handleSave = async () => {
    setSaving(true);
    setErrors([]);
    setError(null);
    try {
      const payload = { name: pluginName, source };
      const check = await pluginsApi.checkPlugin(payload);
      if (!check.ok) {
        setErrors(check.errors);
        return;
      }
      if (isNew) {
        await pluginsApi.createPlugin(payload);
      } else {
        await pluginsApi.updatePlugin(pluginName, { source });
      }
      navigate("/plugins");
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        const detail = e.detail as { errors?: PluginCheckError[] };
        if (Array.isArray(detail?.errors)) {
          setErrors(detail.errors);
        } else {
          setError(e.message);
        }
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page">
      <header className="page-header">
        <h1>{isNew ? "新增自定义插件" : `编辑插件 ${pluginName}`}</h1>
      </header>
      {loading && <p className="muted">加载中…</p>}
      {!loading && (
        <>
          <p className="hint">
            {isBuiltin
              ? "预置插件只读，仅可查看源码（源码在文件系统，不可修改）。"
              : "自定义插件仅可使用 Python 标准库；通过 PluginBase / engine_function 定义函数，保存后即生效。"}
          </p>
          {isNew && (
            <TextField
              label="插件名"
              value={pluginName}
              onChange={(e) => setPluginName(e.target.value)}
              placeholder="小写字母/数字/下划线/连字符，如 my_plugin"
            />
          )}
          <CodeMirror
            value={source}
            height="420px"
            extensions={[python()]}
            readOnly={isBuiltin}
            onChange={(value) => setSource(value)}
          />
          {errors.length > 0 && (
            <div className="check-errors" role="alert">
              <h3>校验失败</h3>
              {errors.map((err, i) => (
                <p key={i}>
                  {err.line != null ? `第 ${err.line} 行` : "加载失败"}: {err.message}
                  {err.constraint ? `（约束：${err.constraint}）` : ""}
                </p>
              ))}
            </div>
          )}
          {error && <ErrorMessage message={error} />}
          <div className="actions">
            {!isBuiltin && (
              <Button onClick={handleSave} disabled={saving || !pluginName.trim()}>
                {saving ? "保存中…" : "保存"}
              </Button>
            )}
            <Link to="/plugins">返回</Link>
          </div>
        </>
      )}
    </div>
  );
}