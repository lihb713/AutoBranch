import { useCallback, useEffect, useRef, useState } from "react";
import {
  fileApi,
  type FileDirectory,
  type FileEntries,
  type FileRecord,
} from "../../api/file";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorMessage } from "../../components/ErrorMessage";

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function joinPath(base: string, name: string): string {
  const left = base.replace(/\/+$/, "");
  const right = name.replace(/^\/+/, "");
  return left ? `${left}/${right}` : right;
}

function parentPath(path: string): string {
  const index = path.lastIndexOf("/");
  return index < 0 ? "" : path.slice(0, index);
}

export function FileManager() {
  const [path, setPath] = useState("");
  const [entries, setEntries] = useState<FileEntries>({
    path: "",
    directories: [],
    files: [],
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dirInputRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(() => {
    setLoading(true);
    fileApi
      .listEntries(path)
      .then((data) => {
        setEntries(data);
        setError(null);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [path]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    const input = dirInputRef.current;
    if (input) {
      input.setAttribute("webkitdirectory", "true");
      input.setAttribute("directory", "true");
    }
  }, []);

  const uploadFile = async (file: File) => {
    setError(null);
    setUploading(true);
    try {
      await fileApi.upload(file, joinPath(path, file.name));
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  };

  const uploadDirectory = async (files: FileList) => {
    setError(null);
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const relative =
          (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
        await fileApi.upload(file, joinPath(path, relative));
      }
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  };

  const createDirectory = async () => {
    const name = window.prompt("目录名称（支持 a/b 嵌套）");
    if (!name?.trim()) return;
    try {
      await fileApi.createDirectory(joinPath(path, name.trim()));
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const renameDirectory = async (directory: FileDirectory) => {
    const next = window.prompt("新的目录路径", directory.path);
    if (!next?.trim() || next.trim() === directory.path) return;
    try {
      await fileApi.renameDirectory(directory.id, next.trim());
      if (path === directory.path || path.startsWith(`${directory.path}/`)) {
        setPath(next.trim() + path.slice(directory.path.length));
      } else {
        reload();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const deleteDirectory = async (directory: FileDirectory) => {
    if (!window.confirm(`确认递归删除目录「${directory.path}」及其全部内容？`)) return;
    try {
      await fileApi.deleteDirectory(directory.id, true);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const removeFile = async (record: FileRecord) => {
    if (!window.confirm(`确认删除文件「${record.path}」？`)) return;
    try {
      await fileApi.delete(record.id);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const breadcrumbs = path ? path.split("/") : [];

  return (
    <div className="page" data-testid="file-manager">
      <header className="page-header">
        <h1>文件管理</h1>
        <div className="tree-table__actions">
          <Button onClick={() => fileInputRef.current?.click()} disabled={uploading}>
            {uploading ? "上传中…" : "上传文件"}
          </Button>
          <Button
            variant="ghost"
            onClick={() => dirInputRef.current?.click()}
            disabled={uploading}
            data-testid="file-upload-directory"
          >
            上传目录
          </Button>
          <Button variant="ghost" onClick={() => void createDirectory()}>
            新建目录
          </Button>
        </div>
      </header>

      <div className="file-breadcrumbs" data-testid="file-breadcrumbs">
        <button type="button" className="link" onClick={() => setPath("")}>
          根目录
        </button>
        {breadcrumbs.map((part, index) => {
          const target = breadcrumbs.slice(0, index + 1).join("/");
          return (
            <span key={target}>
              {" / "}
              <button type="button" className="link" onClick={() => setPath(target)}>
                {part}
              </button>
            </span>
          );
        })}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        className="visually-hidden"
        data-testid="file-upload-input"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void uploadFile(file);
          e.target.value = "";
        }}
      />
      <input
        ref={dirInputRef}
        type="file"
        multiple
        className="visually-hidden"
        data-testid="file-directory-input"
        onChange={(e) => {
          const files = e.target.files;
          if (files && files.length > 0) void uploadDirectory(files);
          e.target.value = "";
        }}
      />

      {error ? <ErrorMessage message={error} /> : null}
      {loading ? (
        <p className="muted">加载中…</p>
      ) : entries.directories.length === 0 && entries.files.length === 0 ? (
        <EmptyState title="当前目录为空" hint="上传文件/目录，或新建目录" />
      ) : (
        <table className="tree-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>路径</th>
              <th>大小</th>
              <th>MD5</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {entries.directories.map((directory) => (
              <tr key={`dir-${directory.id}`} data-testid={`file-dir-${directory.id}`}>
                <td>
                  <button
                    type="button"
                    className="link"
                    onClick={() => setPath(directory.path)}
                  >
                    📁 {directory.name}
                  </button>
                </td>
                <td className="run-cell-json">{directory.path}</td>
                <td>—</td>
                <td>—</td>
                <td>{directory.updated_at}</td>
                <td>
                  <div className="tree-table__actions">
                    <a href={fileApi.downloadPathUrl(directory.path)}>下载目录</a>
                    <button
                      type="button"
                      className="link"
                      onClick={() => void renameDirectory(directory)}
                    >
                      重命名
                    </button>
                    <button
                      type="button"
                      className="link link-danger"
                      onClick={() => void deleteDirectory(directory)}
                    >
                      删除
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {entries.files.map((file) => (
              <tr key={`file-${file.id}`} data-testid={`file-row-${file.id}`}>
                <td>{file.filename}</td>
                <td className="run-cell-json">{file.path}</td>
                <td>{formatSize(file.size)}</td>
                <td className="file-md5" title={file.md5}>
                  {file.md5 ? `${file.md5.slice(0, 12)}…` : "—"}
                </td>
                <td>{file.updated_at}</td>
                <td>
                  <div className="tree-table__actions">
                    <a href={fileApi.downloadPathUrl(file.path)}>下载</a>
                    <button
                      type="button"
                      className="link link-danger"
                      onClick={() => void removeFile(file)}
                    >
                      删除
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {path ? (
        <p>
          <button type="button" className="link" onClick={() => setPath(parentPath(path))}>
            ← 返回上级目录
          </button>
        </p>
      ) : null}
    </div>
  );
}
