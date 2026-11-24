export type NodeInfo = {
  node_type: string;
  node_desc: string;
  parallel?: string | null;
};

export type ActionCall = {
  function: string;
  success: boolean;
  arguments: Record<string, unknown> | null;
  error: string | null;
};

export type NodeReport = {
  node_type: string;
  node_desc: string;
  result: string;
  timestamp: string;
  action_call: ActionCall | null;
  condition_result: boolean | null;
  page_url: string | null;
  screenshot_path: string | null;
  duration?: number | null;
  failure_reason?: string | null;
  function?: string | null;
  arguments?: Record<string, unknown> | null;
  kwargs?: Record<string, unknown> | null;
  returns?: Record<string, unknown> | null;
  details?: Record<string, unknown> | null;
  parallel?: string | null;
};

export type BlackboardVar = {
  path: string;
  type: string;
  value: unknown;
  truncated?: boolean;
  full_length?: number | null;
};

export type RunState = {
  run_id: string;
  status: "pending" | "running" | "success" | "failure";
  progress: number;
  current_node: NodeInfo | null;
  completed: NodeReport[];
  finished: boolean;
  failure_reason: string | null;
  variables?: BlackboardVar[];
};

export type RunStart = {
  run_id: number;
};

export type TypeInfo = {
  token: string;
  constructible: boolean;
  owner?: string;
  custom?: boolean;
  description?: string;
};

export type RunOut = {
  id: number;
  tree_id: number | null;
  tree_name: string;
  status: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown> | null;
  tree_content_hash: string;
  failure_reason: string | null;
  created_at: string | null;
  updated_at: string | null;
  duration: number | null;
  progress: number | null;
  source: string;
  schedule_id: number | null;
};

export type RunScheduleBrief = {
  id: number;
  name: string;
  schedule_mode: "interval" | "cron";
  interval: number | null;
  interval_unit: string | null;
  cron_period: string | null;
  cron_time: string | null;
  cron_weekday: number | null;
};

export type RunDetail = RunOut & {
  content_snapshot: string;
  schedule: RunScheduleBrief | null;
};

export type ReportResponse = { run_id: string; status: string; message?: string } | string;