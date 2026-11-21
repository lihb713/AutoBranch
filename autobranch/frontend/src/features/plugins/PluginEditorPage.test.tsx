import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";
import { pluginsApi } from "../../api/plugins";
import { PluginEditorPage } from "./PluginEditorPage";

vi.mock("@uiw/react-codemirror", () => ({
  default: ({
    value,
    onChange,
  }: {
    value: string;
    onChange: (v: string) => void;
  }) => (
    <textarea
      data-testid="code"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
}));

vi.mock("@codemirror/lang-python", () => ({ python: () => [] }));

vi.mock("../../api/plugins", () => ({
  pluginsApi: {
    getPlugin: vi.fn(),
    listPluginFunctions: vi.fn(),
    checkPlugin: vi.fn(),
    createPlugin: vi.fn(),
    updatePlugin: vi.fn(),
  },
}));

const mockCheck = pluginsApi.checkPlugin as unknown as ReturnType<typeof vi.fn>;

function renderNew() {
  return render(
    <MemoryRouter initialEntries={["/plugins/new"]}>
      <Routes>
        <Route path="/plugins/new" element={<PluginEditorPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PluginEditorPage", () => {
  test("校验失败时显示行号与约束提示", async () => {
    mockCheck.mockResolvedValue({
      ok: false,
      errors: [
        {
          line: 3,
          column: 1,
          type: "constraint",
          message: "自定义插件仅允许标准库，不允许 import requests",
          constraint: "仅标准库",
        },
      ],
    });
    renderNew();
    await userEvent.type(screen.getByLabelText("插件名"), "my-helper");
    await userEvent.click(screen.getByRole("button", { name: "保存" }));
    expect(
      await screen.findByText(/不允许 import requests/),
    ).toBeInTheDocument();
    expect(screen.getByText(/第 3 行/)).toBeInTheDocument();
  });

  test("校验通过时创建插件", async () => {
    mockCheck.mockResolvedValue({ ok: true, errors: [] });
    const create = pluginsApi.createPlugin as unknown as ReturnType<typeof vi.fn>;
    create.mockResolvedValue({ id: 1, name: "my-helper", kind: "custom" });
    renderNew();
    await userEvent.type(screen.getByLabelText("插件名"), "my-helper");
    await userEvent.click(screen.getByRole("button", { name: "保存" }));
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({ name: "my-helper" }),
    );
  });

  test("预置插件默认展示函数详情，可切换源码 Tab", async () => {
    const getPlugin = pluginsApi.getPlugin as unknown as ReturnType<typeof vi.fn>;
    const listFns = pluginsApi.listPluginFunctions as unknown as ReturnType<typeof vi.fn>;
    getPlugin.mockResolvedValue({
      id: 1,
      name: "browser",
      kind: "builtin",
      description: "浏览器",
      functions: ["open"],
      source: "class BrowserPlugin(PluginBase): ...",
      created_at: "",
      updated_at: "",
    });
    listFns.mockResolvedValue([
      {
        full_name: "browser.open",
        plugin: "browser",
        name: "open",
        description: "打开页面",
        returns: { page: "generics" },
        parameters: {
          type: "object",
          properties: { url: { type: "string", description: "URL" } },
          required: ["url"],
        },
        output_param: "save_to",
        user_visible: true,
      },
    ]);
    render(
      <MemoryRouter initialEntries={["/plugins/edit/browser"]}>
        <Routes>
          <Route path="/plugins/edit/:name" element={<PluginEditorPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("browser.open")).toBeInTheDocument();
    expect(screen.getByText(/打开页面/)).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("plugin-tab-source"));
    expect(screen.getByTestId("code")).toBeInTheDocument();
    expect(screen.getByText(/预置插件只读/)).toBeInTheDocument();
  });
});
