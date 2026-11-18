import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FileEntries } from "../../api/file";
import { FileManager } from "./FileManager";

const mocks = vi.hoisted(() => ({
  listEntries: vi.fn(),
  upload: vi.fn(),
  createDirectory: vi.fn(),
  renameDirectory: vi.fn(),
  deleteDirectory: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("../../api/file", () => ({
  fileApi: {
    listEntries: mocks.listEntries,
    upload: mocks.upload,
    createDirectory: mocks.createDirectory,
    renameDirectory: mocks.renameDirectory,
    deleteDirectory: mocks.deleteDirectory,
    delete: mocks.delete,
    downloadPathUrl: (path: string) => `/api/plugins/file/download?path=${path}`,
  },
}));

const ROOT: FileEntries = {
  path: "",
  directories: [
    { id: 1, path: "docs", name: "docs", created_at: "", updated_at: "" },
  ],
  files: [
    {
      id: 2,
      filename: "root.txt",
      path: "root.txt",
      size: 12,
      content_type: "text/plain",
      created_at: "",
      updated_at: "",
    },
  ],
};

const DOCS: FileEntries = {
  path: "docs",
  directories: [],
  files: [
    {
      id: 3,
      filename: "a.txt",
      path: "docs/a.txt",
      size: 3,
      content_type: "text/plain",
      created_at: "",
      updated_at: "",
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listEntries.mockImplementation((path: string) =>
    Promise.resolve(path === "docs" ? DOCS : ROOT),
  );
  mocks.upload.mockResolvedValue({});
  mocks.createDirectory.mockResolvedValue({});
});

describe("FileManager", () => {
  it("展示目录/文件并进入目录", async () => {
    render(<FileManager />);
    expect(await screen.findByTestId("file-dir-1")).toBeInTheDocument();
    fireEvent.click(screen.getByText("📁 docs"));
    expect(await screen.findByText("a.txt")).toBeInTheDocument();
    expect(screen.getByTestId("file-breadcrumbs")).toHaveTextContent("docs");
  });

  it("当前目录上传文件时使用平台路径", async () => {
    render(<FileManager />);
    fireEvent.click(await screen.findByText("📁 docs"));
    await screen.findByText("a.txt");
    const file = new File(["abc"], "up.txt", { type: "text/plain" });
    fireEvent.change(screen.getByTestId("file-upload-input"), {
      target: { files: [file] },
    });
    await waitFor(() =>
      expect(mocks.upload).toHaveBeenCalledWith(file, "docs/up.txt"),
    );
  });

  it("新建目录使用当前路径前缀", async () => {
    vi.spyOn(window, "prompt").mockReturnValue("reports");
    render(<FileManager />);
    await screen.findByTestId("file-dir-1");
    fireEvent.click(screen.getByText("新建目录"));
    await waitFor(() => expect(mocks.createDirectory).toHaveBeenCalledWith("reports"));
  });
});
