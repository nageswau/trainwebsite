import { ApiError } from "@/lib/api";
import { counselingQuery } from "@/lib/managementCounseling";

// ccrm-036 (DEC-SCOPE-269, P1-P9): GET /counselor/performance -- the overseas counselor's own figures for an IST period (the period
// figures are mgmt-018's, without revenue) and their caseload now. The API decides access and every figure; a null percentage has nothing
// to divide. The period lives in the address (`counselingQuery`, the management counseling page's parser).
// ccrm-053 (DEC-SCOPE-325, PF1-PF9): the intake ("Sep 2027") and lead-division filters live in the address too; the Overseas Admin reads
// every overseas counselor (`ADMIN_PERFORMANCE_API`) and one counselor's report (`…/{id}`).
export const PERFORMANCE_HOME = "/overseas/counselor/reports";
export const PERFORMANCE_API = "/api/v1/counselor/performance";
export const PERFORMANCE_UNAVAILABLE = "Your performance figures are unavailable right now. Please try again.";
export const ADMIN_PERFORMANCE_HOME = "/overseas/admin/counselor-performance";
export const ADMIN_PERFORMANCE_API = "/api/v1/overseas-admin/counselor-performance";
export const TEAM_UNAVAILABLE = "Counselor performance is unavailable right now. Please try again.";
export const LEAD_DIVISIONS = [["overseas", "Overseas"], ["it", "IT"]] as const;
export const ADMIN_ROLES = ["overseas_admin", "super_admin"]; // PF6
export const ADMIN_REFUSED = "Overseas Administrator role required";

/** A 422's own message (a bad period or intake), else `fallback`. */
export function errorText(e: unknown, fallback: string): string {
  return e instanceof ApiError && e.status === 422 && typeof e.message === "string" && !e.message.startsWith("[object") ? e.message : fallback;
}

export type PerformanceFigure = { key: string; label: string; definition: string; unit: "count" | "percent"; value: number | null };
export type PerformanceCounts = { applications: number; students: number };
export type PerformanceRow = PerformanceCounts & { stage: string; stage_label: string; sub_status: string | null; sub_status_label: string };
export type CounselorPerformanceReport = {
  from: string; to: string; as_of: string; intake: string | null; division: string | null;
  counselor?: { id: string; full_name: string; active: boolean } | null;
  period: PerformanceFigure[]; now: PerformanceFigure[];
  applications: { rows: PerformanceRow[]; total: PerformanceCounts; definitions: { key: string; label: string; definition: string }[] };
}; // prettier-ignore

export type TeamFigures = {
  full_name: string; leads: number; leads_overseas: number; leads_it: number; leads_assigned: number; calls: number; counseling_sessions: number;
  conversions: number; conversion_pct: number | null; students: number; applications: number; visas_pending: number; visas_approved: number;
  visas_refused: number; enrollments: number;
}; // prettier-ignore
export type TeamRow = TeamFigures & { id: string; active: boolean };
export type TeamColumn = { key: keyof TeamFigures; label: string; definition: string };
export type TeamPerformance = {
  from: string; to: string; as_of: string; intake: string | null; division: string | null; columns: TeamColumn[]; items: TeamRow[]; totals: TeamFigures;
}; // prettier-ignore

export type PerformanceQuery = { from: string; to: string; intake: string; division: string };

/** The address: an impossible date or a repeated value is dropped (this month); the intake is sent as typed, so the API says what is wrong. */
export function performanceQuery(search: Record<string, string | string[] | undefined>): PerformanceQuery {
  const text = (key: string) => (typeof search[key] === "string" ? (search[key] as string).trim() : "");
  return { ...counselingQuery(search), intake: text("intake").slice(0, 80), division: text("division") };
}

function params(query: PerformanceQuery): string {
  const entries = Object.entries(query).filter(([, value]) => value);
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
}

/** The API route (or a page) with the query's non-empty filters. */
export const performanceUrl = (query: PerformanceQuery, api: string = PERFORMANCE_API): string => `${api}${params(query)}`;
