// ccrm-009 (DEC-SCOPE-253): the counselor's / Overseas Admin's student 360 -- tab list and the read-only tab payloads
// (API_CONTRACT.md §12FF). Profile tabs use lib/studentProfile.ts, the notes panel lib/studentNotes.ts.

export const STUDENT_TABS = [
  { key: "overview", label: "Overview" },
  { key: "academic", label: "Academic" },
  { key: "preferences", label: "Preferences" },
  { key: "english", label: "English" },
  { key: "documents", label: "Documents" },
  { key: "applications", label: "Applications" },
  { key: "activities", label: "Activities" },
  { key: "history", label: "History" },
] as const;

export type StudentTab = (typeof STUDENT_TABS)[number]["key"];

export function studentTab(value: string | string[] | undefined): StudentTab {
  const key = Array.isArray(value) ? value[0] : value;
  return STUDENT_TABS.find((t) => t.key === key)?.key ?? "overview";
}

export const student360Url = (id: string, tab: "overview" | "documents" | "activities" | "history") =>
  `/api/v1/counselor/students/${encodeURIComponent(id)}/${tab}`;

export const ACCOUNT_STATUS: Record<string, string> = {
  active: "Active",
  pending_setup: "Waiting for the student to set a password",
  link_expired: "Set-password link expired",
  deactivated: "Deactivated",
};

export type StudentApplication = {
  id: string;
  application_code: string | null;
  university: string;
  course: string | null;
  intake: string | null;
  status: string;
  status_label: string;
  sub_status_label: string | null;
  outcome_summary: string | null;
  next_action: string | null;
  counselor: string | null;
  is_agency: boolean;
  mine: boolean;
  open: boolean;
};

// ccrm-017 (DEC-SCOPE-258): the derived journey stage -- read-only, never stored on an application.
export type StudentJourney = {
  stage: string;
  label: string;
  steps: { key: string; label: string; state: "done" | "current" | "upcoming" }[];
  application: { id: string; application_code: string | null; university: string } | null;
  note: string | null;
};

export type StudentOverview = {
  student: { id: string; full_name: string; student_code: string | null; email: string; phone: string | null };
  account_status: string;
  counselor: { id: string; full_name: string } | null;
  journey: StudentJourney;
  applications: StudentApplication[];
  counts: { applications: number; open_applications: number; documents_to_review: number };
  next_actions: { application_id: string; application_code: string | null; university: string; next_action: string }[];
};

export type StudentDocumentRow = {
  id: string;
  document_type: string;
  document_label: string | null;
  application_code: string | null;
  status: string;
  status_label: string;
  expiry_date: string | null;
  reviewer: string | null;
  reviewed_at: string | null;
  uploaded_at: string;
  can_download: boolean;
};

export type StudentActivities = {
  appointments: { id: string; type: string; scheduled_at: string; mode: string; status: string; staff: string | null }[];
  leads: { id: string; lead_code: string; stage: string; stage_label: string; owner: string | null; href: string | null }[];
};

export type StudentHistoryItem = {
  at: string;
  kind: "status" | "audit" | "document";
  summary: string;
  actor: string | null;
  application_code: string | null;
  notes: string | null;
  reason: string | null;
};
