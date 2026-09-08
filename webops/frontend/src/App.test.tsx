import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { runsApi } from "./api/runs";
import { treesApi } from "./api/trees";

vi.mock("./api/trees", () => ({
  treesApi: { listTrees: vi.fn(), getTree: vi.fn(), createTree: vi.fn(), updateTree: vi.fn(), deleteTree: vi.fn(), checkTree: vi.fn() },
}));

vi.mock("./api/runs", () => ({
  runsApi: {
    runTree: vi.fn(),
    getRunState: vi.fn(),
    getRunReport: vi.fn(),
    getRunTrace: vi.fn(),
    getReportFile: (p: string) => `/api/reports/${p}`,
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(treesApi.listTrees).mockResolvedValue([]);
  vi.mocked(runsApi.getRunState).mockResolvedValue({
    run_id: "5",
    progress: 1,
    current_node: null,
    completed: [],
    finished: true,
    failure_reason: null,
  });
  vi.mocked(runsApi.getRunReport).mockResolvedValue("# 执行报告");
  vi.mocked(runsApi.getRunTrace).mockResolvedValue("# 回溯报告");
});

async function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("路由冒烟", () => {
  it("/ 渲染树列表页", async () => {
    await renderAt("/");
    expect(await screen.findByRole("heading", { name: "行为树" })).toBeInTheDocument();
  });

  it("/editor/:id? 渲染编辑器页", async () => {
    await renderAt("/editor");
    expect(await screen.findByRole("heading", { name: "新建行为树" })).toBeInTheDocument();
  });

  it("/runs/:runId 渲染执行报告页", async () => {
    await renderAt("/runs/5");
    expect(await screen.findByRole("heading", { name: "执行报告 #5" })).toBeInTheDocument();
  });

  it("未知路径重定向到列表", async () => {
    await renderAt("/nope");
    expect(await screen.findByRole("heading", { name: "行为树" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("heading", { name: "新建行为树" })).not.toBeInTheDocument());
  });
});