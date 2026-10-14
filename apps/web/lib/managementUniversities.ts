import type { PerformanceCommission } from "@/lib/commissionLedger";
import { isCalendarDate } from "@/lib/formatDate";
import type { ExpectedRow, ForecastWindow } from "@/lib/partnershipExpected";

// mgmt-023 (EVID-017 §19, spec UD1-UD14): GET /management/universities -- the twelve §19 KPIs, the Management §19 pipeline and the
// expected partnerships, read through from the University Partnership CRM (its totals equal upc-029's). The API decides access (operational
// tier) and every figure; `revenue` is present only for partners (UD10). The period drives Applications, Enrollments and Revenue.
export const UNIVERSITIES_HOME = "/management/universities";
const UNIVERSITIES_API = "/api/v1/management/universities";

export type UniversityKpi = { key: string; label: string; value: number };
export type UniversitiesDashboard = {
  today: string; from: string; to: string; kpis: UniversityKpi[]; revenue?: PerformanceCommission;
  pipeline: { steps: { key: string; label: string; count: number }[]; lost: number; total: number };
  expected: { windows: ForecastWindow[]; undated: number; next_month: { total: number; items: ExpectedRow[] } };
}; // prettier-ignore
export type UniversitiesQuery = { from: string; to: string };

// UD3: the KPIs that cover the period; the rest are "now".
export const PERIOD_KPIS = new Set(["applications", "enrollments"]);

/** The page's address: an impossible date or a repeated value is dropped, so the API answers with this month to date. */
export function universitiesQuery(search: Record<string, string | string[] | undefined>): UniversitiesQuery {
  const day = (key: string) => (typeof search[key] === "string" && isCalendarDate(search[key] as string) ? (search[key] as string) : "");
  return { from: day("from"), to: day("to") };
}

function withQuery(path: string, { from, to }: UniversitiesQuery): string {
  const params = new URLSearchParams({ ...(from ? { from } : {}), ...(to ? { to } : {}) }).toString();
  return params ? `${path}?${params}` : path;
}

export const universitiesUrl = (query: UniversitiesQuery) => withQuery(UNIVERSITIES_API, query);
export const universitiesHref = (query: UniversitiesQuery) => withQuery(UNIVERSITIES_HOME, query);
