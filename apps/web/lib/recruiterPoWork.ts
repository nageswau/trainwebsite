import type { EditableSheet } from "@/components/TargetsEditor";

// pob-009 (spec 2026-11-07-pob-009-po-targets-reports-design.md): PO targets, territory, target companies, the daily plan and
// daily/weekly activity reports. The API computes every figure and decides every rule; these are its shapes, URLs and words.
export type Person = { id: string; full_name: string };
export type TargetCompany = { id: string; added_at: string; company: { id: string; name: string; code: string; territory: string | null; stage: string } };
export type PoSheet = EditableSheet & {
  recruiter: Person; territory: string | null; contacts_reached: number | null; response_rate: number | null; target_companies: TargetCompany[];
};
export type TeamKpi = { key: string; target: number | null; achieved: number | null; percent: number | null };
export type TeamTargets = {
  month: string; month_status: string; editable: boolean; kpis: { key: string; label: string }[];
  items: { recruiter: Person; territory: string | null; kpis: TeamKpi[]; response_rate: number | null }[]; total: number; limit: number; offset: number;
};
export type FollowUpRef = { id: string; reason: string; due_at: string; status: string; priority: string; notes: string | null; company: { id: string; name: string } };
export type PlanItem = { id: string; kind: "follow_up" | "company"; done_at: string | null; follow_up: FollowUpRef | null; company: { id: string; name: string } };
export type Plan = {
  date: string; editable: boolean; items: PlanItem[]; suggested_follow_ups: { follow_up: FollowUpRef }[];
  suggested_companies: { id: string; name: string; code: string; territory: string | null }[];
};
export type Period = "daily" | "weekly";
export type Counts = Record<string, number | null>;
export type Report = {
  recruiter: Person; period: Period; period_start: string; period_end: string; status: "draft" | "submitted"; counts: Counts;
  plan: { planned: number; done: number } | null; note: string | null; submitted_at: string | null; kpis: { key: string; label: string }[];
};
export type ContactRow = { contact: { id: string; name: string }; company: { id: string; name: string }; outreach: number; replied: boolean };
export type Contacts = { total: number; responses: number; response_rate: number | null; items: ContactRow[]; limit: number; offset: number };
export type TeamReports = {
  period: Period; period_start: string; period_end: string; total: number; limit: number; offset: number;
  items: { recruiter: Person; status: "submitted" | "missing"; submitted_at: string | null; outreach: number | null; response_rate: number | null; meetings: number | null }[];
};

const API = "/api/v1/recruiter";
export const MY_TARGETS_URL = `${API}/targets`;
export const TEAM_TARGETS_URL = `${API}/manager/targets`;
export const TARGET_COMPANIES_URL = `${API}/manager/target-companies`;
export const territoryUrl = (userId: string) => `${API}/manager/team/${userId}/territory`;
export const PLAN_URL = `${API}/daily-plan`;
export const PLAN_ITEMS_URL = `${API}/daily-plan/items`;
export const reportUrl = (period: Period, start: string) => `${API}/activity-reports/${period}/${start}`;
export const teamReportsUrl = (period: Period, start: string) => `${API}/manager/activity-reports?period=${period}&start=${start}`;
export const memberReportUrl = (userId: string, period: Period, start: string) => `${API}/manager/activity-reports/${userId}/${period}/${start}`;
export const contactsUrl = (period: Period, start: string, recruiterId?: string) =>
  `${API}/activity-contacts?period=${period}&start=${start}${recruiterId ? `&recruiter_id=${recruiterId}` : ""}&limit=100`;

export const MANAGER_TARGETS_PATH = "/recruiter/manager/targets";
export const MANAGER_REPORTS_PATH = "/recruiter/manager/activity-reports";
export const REPORTS_PATH = "/recruiter/activity-reports";

const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** The Monday (IST date) of the week holding `day` (YYYY-MM-DD). */
export function mondayOf(day: string): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
}

export function addDays(day: string, by: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + by);
  return d.toISOString().slice(0, 10);
}

/** The period and start from the URL: weekly snaps to its Monday; a bad or missing date is today. */
export function chosenPeriod(sp: { period?: string; start?: string }, today: string): { period: Period; start: string } {
  const period: Period = sp.period === "weekly" ? "weekly" : "daily";
  const day = sp.start && DAY.test(sp.start) && sp.start <= today ? sp.start : today;
  return { period, start: period === "weekly" ? mondayOf(day) : day };
}

export const dayLabel = (day: string) =>
  new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${day}T00:00:00Z`));

export const periodLabel = (period: Period, start: string, end: string) => (period === "weekly" ? `Week ${dayLabel(start)} – ${dayLabel(end)}` : dayLabel(start));

export const rateText = (rate: number | null | undefined) => (rate === null || rate === undefined ? "—" : `${rate}%`);

/** Team table cell: achieved / target (percent), "—" parts when unknown. */
export function cellText(kpi: TeamKpi, status: string): string {
  const achieved = status === "future" ? "—" : String(kpi.achieved ?? "—");
  if (kpi.target === null) return achieved;
  return `${achieved} / ${kpi.target}${kpi.percent === null ? "" : ` (${kpi.percent}%)`}`;
}

export const REASON_LABEL: Record<string, string> = {
  new_requirement: "New requirement", jd: "JD", profile_feedback: "Profile feedback", interview_feedback: "Interview feedback", offer_status: "Offer status",
  joining_confirmation: "Joining confirmation", new_openings: "New openings", contract_mou: "Contract / MoU", payment_commercial: "Payment / commercial",
  clarification: "Clarification",
};
