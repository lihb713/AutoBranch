import type { ScheduleRule, ScheduleRuleInput } from "../../types/schedule";
import type { RunScheduleBrief } from "../../types/run";

export const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

export const INTERVAL_UNITS = ["seconds", "minutes", "hours", "days"] as const;

export const UNIT_LABELS: Record<string, string> = {
  seconds: "秒",
  minutes: "分钟",
  hours: "小时",
  days: "天",
};

type ScheduleLike = Pick<
  ScheduleRule | ScheduleRuleInput | RunScheduleBrief,
  "schedule_mode" | "interval" | "interval_unit" | "cron_period" | "cron_time" | "cron_weekday"
>;

export function scheduleModeLabel(rule: ScheduleLike): string {
  if (rule.schedule_mode === "interval") {
    return `每 ${rule.interval} ${rule.interval_unit ? (UNIT_LABELS[rule.interval_unit] ?? rule.interval_unit) : ""}`;
  }
  const time = rule.cron_time ?? "—";
  if (rule.cron_period === "hour") return `每小时 ${time}`;
  if (rule.cron_period === "week") {
    return `每${WEEKDAYS[rule.cron_weekday ?? 0]} ${time}`;
  }
  return `每天 ${time}`;
}

export function runSourceLabel(source: string | null | undefined): string {
  if (source === "schedule") return "调度";
  if (source === "dependency") return "依赖";
  return "手动";
}
