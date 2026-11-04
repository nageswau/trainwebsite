// hrc-035 (DEC-SCOPE-396 K7/K8, API §12KO): the HR Manager's candidate deletion requests and the retention rule.
export const DATA_REQUESTS_URL = "/api/v1/recruiter/candidate-data-requests";
export const RETENTION_URL = "/api/v1/recruiter/candidate-retention";
export const REASON_LIMIT = 500;

export type DataRequestRow = {
  id: string;
  status: "in_progress" | "rejected" | "fulfilled";
  requested_at: string;
  decided_at: string | null;
  rejection_reason: string | null;
  candidate: { id: string; candidate_code: string; name: string; email: string | null; anonymised: boolean } | null;
  open_applications: number;
  held: boolean;
};

export type Retention = {
  months: number | null;
  range: [number, number];
  due_now: number;
  last_run_at: string | null;
  last_run_count: number | null;
  can_edit: boolean;
};

export const STATUS_LABEL: Record<DataRequestRow["status"], string> = { in_progress: "Waiting", rejected: "Declined", fulfilled: "Deleted" };
