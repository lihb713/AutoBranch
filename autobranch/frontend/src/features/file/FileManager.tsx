import { useCallback, useEffect, useRef, useState } from "react";
import { fileApi, type FileRecord } from "../../api/file";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorMessage } from "../../components/ErrorMessage";

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export function FileManager() {
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(() => {
    setLoading(true);
    fileApi
      .list()
      .then(setFiles)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const upload = async (file: File) => {
    setError(null);
    setUploading(true);
    try {
      await fileApi.upload(file);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  };

  const remove = async (record: FileRecord) => {
    if (!window.confirm(`确认删除文件「${record.filename}」？`)) return;
    try {
      await fileApi.delete(record.id);
      setFiles((prev) => prev.filter((f) => f.id !== record.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="page" data-testid="file-manager">
      <header className="page-header">
        <h1>文件管理</h1>
        <Button onClick={() => inputRef.current?.click()} disabled={uploading}>
          {uploading ? "上传中…" : "上传文件"}
        </Button>
      </header>
      <input
        ref={inputRef}
        type="file"
        className="visually-hidden"
        data-testid="file-upload-input"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void upload(file);
          e.target.value = "";
        }}
      />
      {error ? <ErrorMessage message={error} /> : null}
      {loading ? (
        <p className="muted">加载中…</p>
      ) : files.length === 0 ? (
        <EmptyState title="暂无文件" hint="点击「上传文件」添加" />
      ) : (
        <table className="tree-table">
          <thead>
            <tr>
              <th>文件名</th>
              <th>大小</th>
              <th>上传时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {files.map((f) => (
              <tr key={f.id} data-testid={`file-row-${f.id}`}>
                <td>{f.filename}</td>
                <td>{formatSize(f.size)}</td>
                <td>{f.created_at}</td>
                <td>
                  <a href={fileApi.downloadUrl(f.id)}>下载</a>
                  <button className="link" onClick={() => void remove(f)}>
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
