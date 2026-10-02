// AGN-008 (DEC-SCOPE-050): an agency's applications -- the shapes, labels and stage rules the list, detail and forms share. The
// server is the authority (forward-only, enrolled, stale, archived); these only keep the screens from offering a refused action.

export const APPLICATIONS_URL = "/api/v1/workflows/overseas/agent/crm/applications";

export const STAGES = ["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled"] as const;
export const AGENT_MAX_STAGE = "status_tracking";
const STAGE_LABELS: Record<string, string> = {
  enquiry: "Enquiry",
  eligibility_evaluation: "Eligibility evaluation",
  university_selection: "University selection",
  offer: "Offer",
  visa_documentation: "Visa documentation",
  status_tracking: "Status tracking",
  enrolled: "Enrolled",
  withdrawn: "Withdrawn",
};

export function stageLabel(status: string): string {
  if (STAGE_LABELS[status]) return STAGE_LABELS[status];
  const words = status.replaceAll("_", " "); // QA8-11: a legacy value, e.g. "University review"
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export const STATUS_GROUPS = ["all", "draft", "submitted", "offer", "visa", "enrolled", "withdrawn"] as const;
export type StatusGroup = (typeof STATUS_GROUPS)[number];
export const GROUP_LABELS: Record<StatusGroup, string> = {
  all: "All applications",
  draft: "Draft",
  submitted: "Submitted",
  offer: "Offer received",
  visa: "Visa",
  enrolled: "Enrolled",
  withdrawn: "Withdrawn",
};

export function parseGroup(value: string | null | undefined): StatusGroup {
  return (STATUS_GROUPS as readonly string[]).includes(value ?? "") ? (value as StatusGroup) : "all";
}

// The stages an agent may move to next: every later stage up to status_tracking (skips allowed, as counselor /advance allows).
export function nextStages(current: string): string[] {
  if (current === "withdrawn" || current === "enrolled") return [];
  const at = (STAGES as readonly string[]).indexOf(current); // a legacy value counts as before the first stage (-1)
  return STAGES.slice(at + 1, STAGES.indexOf(AGENT_MAX_STAGE) + 1);
}

export function canWithdraw(current: string): boolean {
  return current !== "withdrawn" && current !== "enrolled";
}

export type NearestDeadline = { kind: "application" | "offer"; date: string } | null;

export function deadlineText(nearest: NearestDeadline, today: string): string | null {
  if (!nearest) return null;
  const label = nearest.kind === "offer" ? "Offer deadline" : "Application deadline";
  const days = Math.round((Date.parse(nearest.date) - Date.parse(today)) / 86_400_000);
  if (days < 0) return `${label} ${nearest.date} (past)`;
  if (days === 0) return `${label} ${nearest.date} (today)`;
  if (days <= 7) return `${label} ${nearest.date} (in ${days} day${days === 1 ? "" : "s"})`;
  return `${label} ${nearest.date}`;
}

export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export type AgentApplicationItem = {
  id: string;
  agent_student_id: string | null;
  student: string;
  has_login: boolean;
  university: string;
  course: string | null;
  intake: string;
  status: string;
  application_reference: string | null;
  submitted_on: string | null;
  application_deadline: string | null;
  offer_deadline: string | null;
  nearest_deadline: NearestDeadline;
  next_action: string | null;
  updated_at: string;
};
export type HistoryEntry = { from_status: string | null; to_status: string; next_action: string | null; notes: string | null; changed_by: string | null; created_at: string };
export type AgentApplicationDetail = AgentApplicationItem & {
  university_id: string;
  university_slug: string;
  course_id: string | null;
  created_at: string;
  read_only_reason: "withdrawn" | "archived" | null;
  history: HistoryEntry[];
};

export const READ_ONLY_TEXT: Record<"withdrawn" | "archived", string> = {
  withdrawn: "This application is withdrawn, so it can no longer be changed.",
  archived: "This student is archived. Unarchive them on the Students page to change this application.",
};
