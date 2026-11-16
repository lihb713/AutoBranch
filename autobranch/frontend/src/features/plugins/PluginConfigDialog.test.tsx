import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import { pluginsApi } from "../../api/plugins";
import { PluginConfigDialog } from "./PluginConfigDialog";

vi.mock("../../api/plugins", () => ({
  pluginsApi: {
    getConfig: vi.fn(),
    updateConfig: vi.fn(),
  },
}));

const getConfig = pluginsApi.getConfig as unknown as ReturnType<typeof vi.fn>;
const updateConfig = pluginsApi.updateConfig as unknown as ReturnType<typeof vi.fn>;

describe("PluginConfigDialog", () => {
  test("按 schema 渲染并保存配置", async () => {
    getConfig.mockResolvedValue({ max_file_size: 10 });
    updateConfig.mockResolvedValue({ max_file_size: 5 });
    const onSaved = vi.fn();
    render(
      <PluginConfigDialog
        pluginName="file"
        schema={[
          {
            key: "max_file_size",
            label: "最大文件大小(MB)",
            type: "number",
            default: 10,
          },
        ]}
        onClose={() => {}}
        onSaved={onSaved}
      />,
    );
    const input = await screen.findByLabelText("最大文件大小(MB)");
    expect(input).toHaveValue(10);
    await userEvent.clear(input);
    await userEvent.type(input, "5");
    await userEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(updateConfig).toHaveBeenCalledWith("file", { max_file_size: 5 }));
    expect(onSaved).toHaveBeenCalled();
  });
});
