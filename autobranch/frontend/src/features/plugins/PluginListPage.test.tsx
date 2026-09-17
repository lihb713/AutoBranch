import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";
import { pluginsApi } from "../../api/plugins";
import { PluginListPage } from "./PluginListPage";

vi.mock("../../api/plugins", () => ({
  pluginsApi: {
    listPlugins: vi.fn(),
    listReferences: vi.fn(),
    deletePlugin: vi.fn(),
  },
}));

const mockList = pluginsApi.listPlugins as unknown as ReturnType<typeof vi.fn>;

describe("PluginListPage", () => {
  test("渲染插件列表并标记预置/自定义", async () => {
    mockList.mockResolvedValue([
      {
        id: 1,
        name: "browser",
        kind: "builtin",
        description: "浏览器",
        functions: ["open", "extract"],
        created_at: "",
        updated_at: "",
      },
      {
        id: 2,
        name: "my-helper",
        kind: "custom",
        description: "我的",
        functions: ["hello"],
        created_at: "",
        updated_at: "",
      },
    ]);
    render(
      <MemoryRouter>
        <PluginListPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("browser")).toBeInTheDocument();
    expect(screen.getByText("my-helper")).toBeInTheDocument();
    expect(screen.getByText("预置")).toBeInTheDocument();
    expect(screen.getByText("自定义")).toBeInTheDocument();
    // 预置插件只读，不提供编辑/删除
    expect(screen.getByText("只读")).toBeInTheDocument();
  });
});