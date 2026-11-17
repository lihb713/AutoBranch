import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ScheduleRule } from "../../types/schedule";
import type { RunOut } from "../../types/run";
import { ScheduleListPage } from "./ScheduleListPage";

const mocks = vi.hoisted(() => ({
  listSchedules: vi.fn(),
  createSchedule: vi.fn(),
  updateSchedule: vi.fn(),
  deleteSchedule: vi.fn(),
  toggleSchedule: vi.fn(),
  runScheduleNow: vi.fn(),
  listScheduleRuns: vi.fn(),
  listTrees: vi.fn(),
}));

vi.mock("../../api/schedules", () => ({
  schedulesApi: {
    listSchedules: mocks.listSchedules,
    createSchedule: mocks.createSchedule,
    updateSchedule: mocks.updateSchedule,
    deleteSchedule: mocks.deleteSchedule,
    toggleSchedule: mocks.toggleSchedule,
    runScheduleNow: mocks.runScheduleNow,
    listScheduleRuns: mocks.listScheduleRuns,
  },
}));

vi.mock("../../api/trees", () => ({
  treesApi: { listTrees: mocks.listTrees },
}));

const RULE: ScheduleRule = {
  id: 1,
  name: "每日汇总",
  target_tree_id: 10,
  target_tree_name: "销售汇总",
  schedule_mode: "cron",
  interval: null,
  interval_unit: null,
  cron_period: "day",
  cron_time: "09:00",
  cron_weekday: null,
  dependencies: [],
  on_failure: "immediate",
  max_retries: 3,
  retry_interval: 60,
  on_missed: "run",
  inputs: {},
  last_run_at: null,
  last_run_id: null,
  last_status: "success",
  last_error: null,
  next_run_at: "2026-01-02T09:00:00",
  enabled: true,
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

const RUN: RunOut = {
  id: 7,
  tree_id: 10,
  tree_name: "销售汇总",
  status: "success",
  inputs: {},
  outputs: null,
  tree_content_hash: "abcdef123456",
  failure_reason: null,
  created_at: "2026-01-01T09:00:00",
  updated_at: "2026-01-01T09:00:10",
  duration: 10,
  progress: null,
  source: "schedule",
  schedule_id: 1,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ScheduleListPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listSchedules.mockResolvedValue([RULE]);
  mocks.listTrees.mockResolvedValue([
    { id: 10, name: "销售汇总", status: "published", created_at: "x", updated_at: "x", inputs: {} },
  ]);
  mocks.toggleSchedule.mockResolvedValue({ ...RULE, enabled: false });
  mocks.runScheduleNow.mockResolvedValue({ run_id: 7 });
  mocks.listScheduleRuns.mockResolvedValue([RUN]);
  mocks.createSchedule.mockResolvedValue(RULE);
});

describe("ScheduleListPage", () => {
  it("渲染调度规则与调度方式", async () => {
    renderPage();
    expect(await screen.findByTestId("schedule-row-1")).toBeInTheDocument();
    expect(screen.getByText("每日汇总")).toBeInTheDocument();
    expect(screen.getByText("每天 09:00")).toBeInTheDocument();
    expect(screen.getByText("下次执行")).toBeInTheDocument();
  });

  it("立即执行 → 调用 API 并显示触发的 run_id", async () => {
    renderPage();
    await screen.findByTestId("schedule-row-1");
    fireEvent.click(screen.getByTestId("schedule-run-now-1"));
    await waitFor(() => expect(mocks.runScheduleNow).toHaveBeenCalledWith(1));
    expect(await screen.findByTestId("schedule-notice")).toHaveTextContent("已触发执行 #7");
  });

  it("新建调度 → 提交表单", async () => {
    renderPage();
    await screen.findByTestId("schedule-row-1");
    fireEvent.click(screen.getByTestId("new-schedule"));
    fireEvent.change(screen.getByTestId("schedule-name"), {
      target: { value: "新规则" },
    });
    fireEvent.click(screen.getByTestId("schedule-save"));
    await waitFor(() =>
      expect(mocks.createSchedule).toHaveBeenCalledWith(
        expect.objectContaining({ name: "新规则", target_tree_id: 10 }),
      ),
    );
  });

  it("切换启用状态", async () => {
    renderPage();
    await screen.findByTestId("schedule-row-1");
    fireEvent.click(screen.getByTestId("schedule-toggle-1"));
    await waitFor(() => expect(mocks.toggleSchedule).toHaveBeenCalledWith(1));
    expect(await screen.findByText("已停用")).toBeInTheDocument();
  });

  it("执行记录弹窗展示关联实例", async () => {
    renderPage();
    await screen.findByTestId("schedule-row-1");
    fireEvent.click(screen.getByTestId("schedule-runs-1"));
    await waitFor(() => expect(mocks.listScheduleRuns).toHaveBeenCalledWith(1));
    const dialog = await screen.findByTestId("schedule-records");
    expect(dialog).toHaveTextContent("销售汇总");
    expect(dialog).toHaveTextContent("schedule");
  });
});
