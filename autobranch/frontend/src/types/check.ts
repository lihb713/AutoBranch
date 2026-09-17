export type CheckIssue = {
  code: string;
  message: string;
  rule: string;
  loc: string | null;
};

export type CheckReport = {
  ok: boolean;
  issues: CheckIssue[];
};