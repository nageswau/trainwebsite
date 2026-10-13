import { isCalendarDate } from "@/lib/formatDate";

// mgmt-020 (EVID-017 §16, spec BD1-BD12): GET /management/bdm -- one BDM type's figures, company-wide, for an IST period. The API decides
// access and every figure; a figure that is not tracked has `value: null`.
export const BDM_DASHBOARD_HOME = "/management/bdm";
export const BDM_DASHBOARD_API = "/api/v1/management/bdm";
export const BDM_DASHBOARD_TYPES = [
  { type: "agent", label: "Agent BDM" }, { type: "school", label: "School BDM" }, { type: "college", label: "College BDM" },
] as const; // prettier-ignore

export type BdmDashboardType = (typeof BDM_DASHBOARD_TYPES)[number]["type"];
export type BdmDashboardFigure = { key: string; label: string; definition: string; basis: "period" | "now"; tracked: boolean; value: number | null };
export type BdmDashboard = { type: BdmDashboardType; label: string; from: string; to: string; as_of: string; bdm_count: number; figures: BdmDashboardFigure[] };
export type BdmDashboardQuery = { type: BdmDashboardType; from: string; to: string };

/** The page's address: an unknown type, an impossible date or a repeated value is dropped, so the API answers with its defaults. */
export function bdmDashboardQuery(search: Record<string, string | string[] | undefined>): BdmDashboardQuery {
  const day = (key: string) => (typeof search[key] === "string" && isCalendarDate(search[key] as string) ? (search[key] as string) : "");
  const type = BDM_DASHBOARD_TYPES.find((t) => t.type === search.type)?.type ?? "agent";
  return { type, from: day("from"), to: day("to") };
}

function params({ type, from, to }: BdmDashboardQuery): string {
  return new URLSearchParams({ type, ...(from ? { from } : {}), ...(to ? { to } : {}) }).toString();
}

export const bdmDashboardUrl = (query: BdmDashboardQuery) => `${BDM_DASHBOARD_API}?${params(query)}`;

/** A tab's link: its type, keeping the chosen period. */
export const bdmDashboardHref = (query: BdmDashboardQuery, type: BdmDashboardType) => `${BDM_DASHBOARD_HOME}?${params({ ...query, type })}`;
