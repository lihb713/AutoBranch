import type {
  ScheduleRule,
  ScheduleRuleInput,
  ScheduleRunNow,
} from "../types/schedule";
import type { RunOut } from "../types/run";
import { request } from "./request";

export const schedulesApi = {
  listSchedules: () => request<ScheduleRule[]>("/schedules"),

  createSchedule: (payload: ScheduleRuleInput) =>
    request<ScheduleRule>("/schedules", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateSchedule: (id: number, payload: ScheduleRuleInput) =>
    request<ScheduleRule>(`/schedules/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  deleteSchedule: (id: number) =>
    request<void>(`/schedules/${id}`, { method: "DELETE" }),

  toggleSchedule: (id: number) =>
    request<ScheduleRule>(`/schedules/${id}/toggle`, { method: "PATCH" }),

  runScheduleNow: (id: number) =>
    request<ScheduleRunNow>(`/schedules/${id}/run`, { method: "POST" }),

  listScheduleRuns: (id: number) =>
    request<RunOut[]>(`/schedules/${id}/runs`),
};
