import type { HealthRag } from "@/lib/managementHealth";
import type { MeetingKind, MeetingStatus } from "@/lib/managementMeetings";
import type { TaskBand, TaskPriority } from "@/lib/managementTasks";
import type { DiscussionStatus } from "@/lib/managementDiscussions";

// mgmt-031 (EVID-017 §31, spec HM1-HM14): GET /management/home -- the partner home. The API leaves every money key out for the super
// admin (HM2), so each one is optional here and the page shows what it is given.
export const HOME_API = "/api/v1/management/home";

type Person = { id: string; full_name: string; role: string };
export type HomeUrgentKey = "overdue_tasks" | "overdue_decisions" | "red_health" | "overdue_receivables";
export type HomeDiscussion = { id: string; topic: string; discussion_date: string; decision: string | null; responsible: Person | null; deadline: string | null; status: DiscussionStatus };
export type HomeMeeting = { id: string; title: string; kind: MeetingKind; starts_at: string; status: MeetingStatus };
export type HomeTask = { id: string; title: string; priority: TaskPriority; deadline: string; status: string; band: TaskBand | null };
export type HomeTargetRow = { item_id: string; text: string; kpi_label: string; unit: string; target: string; actual: string; achievement: number };

export type ManagementHome = {
  as_of: string;
  month: string;
  label: string;
  scope: "business" | "operational";
  snapshot: {
    students: number; applications: number; enrollments: number;
    revenue?: string; expenses?: string; profit?: string; cash?: { amount: string | null; month: string | null };
  };
  urgent: { key: HomeUrgentKey; label: string; count: number; amount?: string }[];
  pending_decisions: { items: HomeDiscussion[]; total: number };
  meetings: { items: HomeMeeting[] };
  targets: { month: string; label: string; rows: HomeTargetRow[]; row_total: number; free_text: { total: number; done: number } } | null;
  financial_position?: {
    receivables: string; receivables_overdue: string; pending_invoices: { count: number; amount: string };
    balance_month: string | null; cash_bank: string | null; payables: string | null; tax_liabilities: string | null;
  };
  growth: { month: string; score: number | null; rag: HealthRag | null; factors: { key: string; label: string; change: number | null; rag: HealthRag | null }[] };
  my_tasks: { items: HomeTask[]; counts: Record<"overdue" | "today" | "week" | "later" | "completed", number> };
  recent_discussions: { items: HomeDiscussion[]; total: number };
  next_plan: { month: string; label: string; plan: { status: string; item_count: number; kpi_count: number } | null };
};

// HM5: where each urgent issue is listed.
export const URGENT_HREF: Record<HomeUrgentKey, string> = {
  overdue_tasks: "/management/tasks?view=everyone",
  overdue_decisions: "/management/discussions#pending-decisions",
  red_health: "/management/health",
  overdue_receivables: "/management/accounts",
};

/** HM3: by the IST hour -- morning before 12, afternoon before 17, evening after. */
export function greeting(now: Date = new Date()): string {
  const hour = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hourCycle: "h23", timeZone: "Asia/Kolkata" }).format(now));
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

export function firstName(fullName: string): string {
  return fullName.trim().split(/\s+/)[0] || fullName;
}

/** HM10: "+12.5%" / "−4%" / "—" for a month-on-month change. */
export function changeText(change: number | null): string {
  if (change === null) return "—";
  return `${change > 0 ? "+" : change < 0 ? "−" : ""}${Math.abs(change).toLocaleString("en-IN")}%`;
}
