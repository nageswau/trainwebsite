import { isCalendarDate } from "@/lib/formatDate";

// mgmt-024 (EVID-017 §20, spec MF1-MF18): GET /management/applications -- the eleven funnel stages in source order (`value` null = not
// tracked, M9), the withdrawn count, the applied filters and the dropdown choices. The API decides access (operational tier) and every
// count; the page holds the filters in the address (a GET form), so refresh, back and shared links keep them.
export const APPLICATIONS_HOME = "/management/applications";
export const APPLICATIONS_API = "/api/v1/management/applications";

export const FUNNEL_FILTER_KEYS = ["date_from", "date_to", "agency", "counselor", "country", "university", "course", "intake", "staff", "status"] as const;
export type FunnelFilterKey = (typeof FUNNEL_FILTER_KEYS)[number];
export type FunnelFilters = Record<FunnelFilterKey, string>;
export const EMPTY_FUNNEL_FILTERS: FunnelFilters = Object.fromEntries(FUNNEL_FILTER_KEYS.map((key) => [key, ""])) as FunnelFilters;

export type FunnelChoice = { value: string; label: string };
export type FunnelStage = { key: string; label: string; tracked: boolean; value: number | null };
export type FunnelOptionKey = "agencies" | "counselors" | "countries" | "universities" | "courses" | "intakes" | "staff" | "statuses";
export type ApplicationFunnel = {
  filters: Record<FunnelFilterKey, string | null>;
  stages: FunnelStage[];
  withdrawn: number;
  options: Record<FunnelOptionKey, FunnelChoice[]>;
};

const UUID_SHAPE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const NONE_ALLOWED = new Set<FunnelFilterKey>(["agency", "counselor"]); // "none" = no agency / no counselor (MF12)
function valid(key: FunnelFilterKey, value: string): boolean {
  if (key === "date_from" || key === "date_to") return isCalendarDate(value);
  if (key === "intake" || key === "status") return value.trim() !== "" && value.length <= (key === "intake" ? 80 : 50); // the API's limits
  return UUID_SHAPE.test(value) || (NONE_ALLOWED.has(key) && value === "none");
}

/** The filters from the page's search params. A repeated, malformed or unknown value only comes from a hand-edited address and is dropped,
 * so the API's only 422 the page shows is its own worded one (the date order). */
export function funnelFilters(search: Record<string, string | string[] | undefined>): FunnelFilters {
  const filters = { ...EMPTY_FUNNEL_FILTERS };
  for (const key of FUNNEL_FILTER_KEYS) {
    const value = search[key];
    if (typeof value === "string" && valid(key, value)) filters[key] = value;
  }
  return filters;
}

export function hasFilters(filters: FunnelFilters): boolean {
  return FUNNEL_FILTER_KEYS.some((key) => filters[key] !== "");
}

function withQuery(path: string, filters: FunnelFilters): string {
  const query = new URLSearchParams();
  for (const key of FUNNEL_FILTER_KEYS) if (filters[key]) query.set(key, filters[key]);
  const text = query.toString();
  return text ? `${path}?${text}` : path;
}

export const applicationsUrl = (filters: FunnelFilters) => withQuery(APPLICATIONS_API, filters);
/** QA24-01: the page's own address for these filters -- only the set ones, so a link is short and shareable. */
export const applicationsHref = (filters: FunnelFilters) => withQuery(APPLICATIONS_HOME, filters);

/** A stage's whole-number percentage of the applications created (0 when none were). */
export function stageShare(value: number, created: number): number {
  return created > 0 ? Math.round((value * 100) / created) : 0;
}

/** QA24-03: the share in words; a non-zero stage that rounds to 0% reads "Less than 1%". */
export function shareText(value: number, created: number): string {
  const share = stageShare(value, created);
  return `${value > 0 && share === 0 ? "Less than 1" : share}% of applications created`;
}
