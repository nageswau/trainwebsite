import { isCalendarDate } from "@/lib/formatDate";

// mgmt-016 (EVID-017 §11, spec SF1-SF16): GET /management/funnel -- the lead journey, then the IT training and abroad education paths,
// for an IST period, optionally broken down by one dimension. The API decides access and every count; a breakdown's rows plus Unknown
// equal each stage's value.
export const FUNNEL_HOME = "/management/funnel";
export const FUNNEL_API = "/api/v1/management/funnel";

// §11's nine breakdowns in source order (the select needs them even when the API answered with an error).
export const FUNNEL_DIMENSIONS = [
  { key: "country", label: "Country" }, { key: "course", label: "Course" }, { key: "agent", label: "Agent" }, { key: "school", label: "School" },
  { key: "counselor", label: "Counselor" }, { key: "source", label: "Marketing source" }, { key: "bdm", label: "BDM" }, { key: "intake", label: "Intake" },
  { key: "branch", label: "Branch" },
] as const; // prettier-ignore
export type FunnelDimensionKey = (typeof FUNNEL_DIMENSIONS)[number]["key"];

export type FunnelPath = { key: string; label: string };
export type FunnelStage = { key: string; label: string; path: string; definition: string; value: number };
export type FunnelDimension = { key: string; label: string; tracked: boolean; stages: string[] };
export type FunnelRow = { value: string; label: string; counts: Record<string, number> };
export type FunnelBreakdown = { by: string; label: string; tracked: boolean; stages: string[]; rows: FunnelRow[]; unknown: Record<string, number> };
export type StudentFunnel = {
  from: string; to: string; as_of: string; paths: FunnelPath[]; stages: FunnelStage[]; dimensions: FunnelDimension[]; breakdown: FunnelBreakdown | null;
}; // prettier-ignore
export type FunnelQuery = { from: string; to: string; by: FunnelDimensionKey | "" };

const isDimension = (value: string): value is FunnelDimensionKey => FUNNEL_DIMENSIONS.some((d) => d.key === value);

/** The page's address: an impossible date, an unknown breakdown or a repeated value is dropped, so the API answers with its default. */
export function funnelQuery(search: Record<string, string | string[] | undefined>): FunnelQuery {
  const day = (key: string) => (typeof search[key] === "string" && isCalendarDate(search[key] as string) ? (search[key] as string) : "");
  const by = typeof search.by === "string" && isDimension(search.by) ? search.by : "";
  return { from: day("from"), to: day("to"), by };
}

export function funnelUrl({ from, to, by }: FunnelQuery): string {
  const params = new URLSearchParams({ ...(from ? { from } : {}), ...(to ? { to } : {}), ...(by ? { by } : {}) }).toString();
  return params ? `${FUNNEL_API}?${params}` : FUNNEL_API;
}
