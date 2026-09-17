export type NodeInfo = {
  node_type: string;
  node_desc: string;
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
};

export type BlackboardVar = {
  path: string;
  type: string;
  value: unknown;
};

export type RunState = {
  run_id: string;
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

export type ReportResponse = { run_id: string; status: string; message?: string } | string;