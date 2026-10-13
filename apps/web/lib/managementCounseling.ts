import { isCalendarDate } from "@/lib/formatDate";

// mgmt-018 (EVID-017 §13, spec CS1-CS12): GET /management/counseling -- every counselor's figures and the totals for an IST period. The
// API decides access and every figure: `calls` is not tracked (null) and `revenue` is null unless `revenue_visible` (partners).
export const COUNSELING_HOME = "/management/counseling";
export const COUNSELING_API = "/api/v1/management/counseling";

export type CounselingFigureKey = "leads_assigned" | "calls" | "counseling_sessions" | "follow_ups" | "conversions" | "revenue" | "conversion_pct";
export type CounselingFigure = { key: CounselingFigureKey; label: string; definition: string; tracked: boolean };
export type CounselingFigures = {
  leads_assigned: number; calls: number | null; counseling_sessions: number; follow_ups: number; conversions: number;
  revenue: string | null; conversion_pct: number | null;
}; // prettier-ignore
export type CounselorRow = CounselingFigures & { id: string; full_name: string; division: string; active: boolean };
export type CounselingGroup = CounselingFigures & { division: string | null; label: string; counselor_count: number };
export type CounselingDashboard = {
  from: string; to: string; as_of: string; revenue_visible: boolean; figures: CounselingFigure[];
  total: CounselingGroup; divisions: CounselingGroup[]; counselors: CounselorRow[];
}; // prettier-ignore
export type CounselingQuery = { from: string; to: string };

/** The page's address: an impossible date or a repeated value is dropped, so the API answers with this month. */
export function counselingQuery(search: Record<string, string | string[] | undefined>): CounselingQuery {
  const day = (key: string) => (typeof search[key] === "string" && isCalendarDate(search[key] as string) ? (search[key] as string) : "");
  return { from: day("from"), to: day("to") };
}

export function counselingUrl({ from, to }: CounselingQuery): string {
  const params = new URLSearchParams({ ...(from ? { from } : {}), ...(to ? { to } : {}) }).toString();
  return params ? `${COUNSELING_API}?${params}` : COUNSELING_API;
}

export const formatCount = (value: number) => value.toLocaleString("en-IN");
export const formatPct = (value: number) => `${value.toFixed(1)}%`;
