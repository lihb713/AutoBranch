export type ScheduleMode = "interval" | "cron";
export type IntervalUnit = "seconds" | "minutes" | "hours" | "days";
export type CronPeriod = "hour" | "day" | "week";
export type OnFailure = "immediate" | "next_schedule";
export type OnMissed = "run" | "skip";

export type ScheduleRule = {
  id: number;
  name: string;
  target_tree_id: number;
  target_tree_name: string;
  schedule_mode: ScheduleMode;
  interval: number | null;
  interval_unit: IntervalUnit | null;
  cron_period: CronPeriod | null;
  cron_time: string | null;
  cron_weekday: number | null;
  dependencies: number[];
  on_failure: OnFailure;
  max_retries: number;
  retry_interval: number;
  on_missed: OnMissed;
  inputs: Record<string, unknown>;
  last_run_at: string | null;
  last_run_id: number | null;
  last_status: string | null;
  last_error: string | null;
  next_run_at: string | null;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type ScheduleRuleInput = {
  name: string;
  target_tree_id: number;
  schedule_mode: ScheduleMode;
  interval: number | null;
  interval_unit: IntervalUnit | null;
  cron_period: CronPeriod | null;
  cron_time: string | null;
  cron_weekday: number | null;
  dependencies: number[];
  on_failure: OnFailure;
  max_retries: number;
  retry_interval: number;
  on_missed: OnMissed;
  inputs: Record<string, unknown>;
  enabled: boolean;
};

export type ScheduleRunNow = {
  run_id: number;
};
