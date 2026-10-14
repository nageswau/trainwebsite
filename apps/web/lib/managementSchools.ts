import { isCalendarDate } from "@/lib/formatDate";

// mgmt-022 (EVID-017 §18, spec SD1-SD16): GET /management/schools -- the §18 school figures and every school's row; PATCH
// /management/schools/{id} sets a school's contract / renewal value. The API decides access and every figure: `revenue`, `contract_value`
// and `renewal_value` are null unless `money_visible` (the finance tier: partners and the accountant).
export const SCHOOLS_HOME = "/management/schools";
export const SCHOOLS_API = "/api/v1/management/schools";

export type SchoolCountKey = "students" | "teachers" | "parents" | "career_guidance" | "psychometric_tests" | "academic_results";
export type SchoolMoneyKey = "revenue" | "contract_value" | "renewal_value";
export type SchoolFigureKey = "schools_contacted" | "meetings" | "proposals" | "mous" | "active_schools" | SchoolCountKey | "profile_completion" | "revenue";
export type SchoolFigure = { key: SchoolFigureKey; label: string; definition: string; basis: "period" | "now" };
type SchoolCounts = Record<SchoolCountKey, number> & Record<SchoolMoneyKey, string | null> & { profile_completion: number | null };
export type SchoolTotals = SchoolCounts & {
  schools_contacted: number; meetings: number; proposals: number; mous: number; active_schools: number; contracts_not_entered: number | null;
}; // prettier-ignore
export type SchoolRow = SchoolCounts & { id: string; name: string; tier: string | null; active: boolean; renewal_due: boolean; tier_valid_until: string | null };
export type SchoolsDashboard = {
  from: string; to: string; as_of: string; money_visible: boolean; figures: SchoolFigure[]; totals: SchoolTotals; untagged_revenue: string | null;
  schools: SchoolRow[];
}; // prettier-ignore
export type SchoolsQuery = { from: string; to: string };
export type SchoolValues = { id: string; contract_value: string | null; renewal_value: string | null };

/** The page's address: an impossible date or a repeated value is dropped, so the API answers with this month. */
export function schoolsQuery(search: Record<string, string | string[] | undefined>): SchoolsQuery {
  const day = (key: string) => (typeof search[key] === "string" && isCalendarDate(search[key] as string) ? (search[key] as string) : "");
  return { from: day("from"), to: day("to") };
}

export function schoolsUrl({ from, to }: SchoolsQuery): string {
  const params = new URLSearchParams({ ...(from ? { from } : {}), ...(to ? { to } : {}) }).toString();
  return params ? `${SCHOOLS_API}?${params}` : SCHOOLS_API;
}
