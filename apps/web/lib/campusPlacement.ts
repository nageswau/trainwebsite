// pob-015 (DEC-SCOPE-426, API §12LS): vacancies shared with a college, its students' outcomes, the campus calendar and the TPO widget.
import { collegeUrl } from "@/lib/recruiterColleges";

export const CAMPUS_CALENDAR_URL = "/api/v1/recruiter/campus-calendar";
export const CAMPUS_SUMMARY_URL = "/api/v1/recruiter/campus-summary";
export const vacanciesUrl = (orgId: string) => collegeUrl(orgId, "vacancies");
export const vacancyOptionsUrl = (orgId: string, q: string) => `${collegeUrl(orgId, "vacancy-options")}${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`;
export const sharesUrl = (orgId: string, shareId?: string) => (shareId ? collegeUrl(orgId, "vacancy-shares", shareId) : collegeUrl(orgId, "vacancy-shares"));

export const RESPONSES = ["awaiting", "interested", "declined", "no_response"] as const;
export const RESPONSE_LABEL: Record<string, string> = { awaiting: "Awaiting reply", interested: "Interested", declined: "Declined", no_response: "No response" };
export const OUTCOME_LABELS: [keyof Outcomes, string][] = [
  ["applications", "Applications"], ["shortlisted", "Shortlisted"], ["interviewed", "Interviewed"], ["offered", "Offered"], ["joined", "Joined"],
];
export const DRIVE_STATUS_LABEL: Record<string, string> = { planned: "Planned", completed: "Completed", cancelled: "Cancelled" };

export type Outcomes = { applications: number; students: number; shortlisted: number; interviewed: number; offered: number; joined: number; external: number };
export type VacancyShare = {
  id: string; requirement: { id: string; code: string; title: string }; shared_on: string; channel: string; template: { id: string; name: string } | null;
  notes: string | null; response: string; response_note: string | null; responded_at: string | null; responded_by_name: string | null; shared_by_name: string;
};
export type Vacancies = { shares: VacancyShare[]; share_total: number; outcomes: Outcomes; can_share: boolean };
export type VacancyOption = { id: string; code: string; title: string; company_name: string };
export type CampusItem = {
  kind: "drive" | "event" | "batch"; id: string; date: string; end_date: string | null; title: string; code: string | null; status: string | null;
  event_kind: string | null; student_count: number | null; college: { id: string; code: string; name: string };
};
export type CampusCalendarData = { from: string; to: string; items: CampusItem[]; truncated: boolean };
export type CampusSummary = { colleges: number; shared_30d: number; awaiting: number; upcoming_30d: number; upcoming_truncated: boolean; outcomes: Outcomes };

export function isVacanciesBody(data: unknown): data is { vacancies: Vacancies } {
  const v = (data as { vacancies?: Partial<Vacancies> } | null)?.vacancies;
  return !!v && Array.isArray(v.shares) && typeof v.share_total === "number" && !!v.outcomes;
}

export function isCalendarData(data: unknown): data is CampusCalendarData {
  const d = data as Partial<CampusCalendarData> | null;
  return !!d && Array.isArray(d.items) && typeof d.from === "string" && typeof d.to === "string";
}

export const isSummary = (data: unknown): data is CampusSummary => !!data && typeof (data as CampusSummary).colleges === "number" && !!(data as CampusSummary).outcomes;

/** "2026-11" -> the month's first and last day; anything else -> null (the page then shows the current month). */
export function monthRange(month: string | undefined | null): { from: string; to: string } | null {
  const m = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(month ?? "");
  if (!m) return null;
  const year = Number(m[1]);
  const index = Number(m[2]);
  const last = new Date(Date.UTC(year, index, 0)).getUTCDate();
  return { from: `${m[1]}-${m[2]}-01`, to: `${m[1]}-${m[2]}-${String(last).padStart(2, "0")}` };
}

/** The month before or after "YYYY-MM". */
export function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + by, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function calendarQuery(range: { from: string; to: string }, collegeId?: string | null): string {
  const params = new URLSearchParams({ from: range.from, to: range.to });
  if (collegeId) params.set("college_id", collegeId);
  return params.toString();
}
