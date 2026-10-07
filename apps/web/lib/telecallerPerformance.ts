// tel-023 (DEC-SCOPE-109, API §12AC): the manager performance comparison -- types, the columns, and the URL rules. Every figure is
// computed by the API (services/telecaller_performance.py on tel-021's metrics); the page only lays it out.
import { dayParam } from "@/lib/telecallerMetrics";

export const COUNT_COLUMNS = [
  { key: "leads", label: "Leads" },
  { key: "calls", label: "Calls" },
  { key: "connected", label: "Connected" },
  { key: "qualified", label: "Qualified" },
  { key: "appointments", label: "Appointments" },
  { key: "conversions", label: "Conversions" },
] as const;
export type CountKey = (typeof COUNT_COLUMNS)[number]["key"];
export type SortKey = "name" | CountKey;
export type SortDir = "asc" | "desc";

export type PerformanceRow = { user_id: string; full_name: string; team: string; active: boolean; status: string } & Record<CountKey, number>;
export type Performance = {
  date_from: string; date_to: string; team: string | null; sort: SortKey; dir: SortDir; teams: string[];
  items: PerformanceRow[]; totals: Record<CountKey, number>;
};
export type PerformanceParams = { date_from?: string; date_to?: string; team?: string; sort?: SortKey; dir?: SortDir };

export const PERFORMANCE_URL = "/api/v1/telecaller/manager/performance";
export const TEAM_LABEL: Record<string, string> = { it: "IT", overseas: "Overseas" };
const SORTS: SortKey[] = ["name", ...COUNT_COLUMNS.map((c) => c.key)];

/** Only well-formed values reach the API, so its only 422s are the range rules, which carry a sentence to show. */
export function performanceParams(raw: Record<string, string | undefined>): PerformanceParams {
  const sort = SORTS.find((s) => s === raw.sort);
  return {
    date_from: dayParam(raw.date_from),
    date_to: dayParam(raw.date_to),
    team: raw.team && raw.team in TEAM_LABEL ? raw.team : undefined,
    sort,
    dir: raw.dir === "asc" || raw.dir === "desc" ? raw.dir : undefined,
  };
}

export function performanceQuery(params: PerformanceParams): string {
  const query = new URLSearchParams(Object.entries(params).filter((entry): entry is [string, string] => !!entry[1])).toString();
  return query ? `?${query}` : "";
}

/** A header link: the current column flips direction; another column starts high-to-low (names A-Z). */
export const nextDir = (data: Performance, key: SortKey): SortDir =>
  data.sort === key ? (data.dir === "desc" ? "asc" : "desc") : key === "name" ? "asc" : "desc";

export function sortHref(base: string, data: Performance, key: SortKey): string {
  const dir = nextDir(data, key);
  return base + performanceQuery({ date_from: data.date_from, date_to: data.date_to, team: data.team ?? undefined, sort: key, dir });
}

export const ariaSort = (data: Performance, key: SortKey) => (data.sort !== key ? "none" : data.dir === "asc" ? "ascending" : "descending");

export const csvFilename = (data: Performance) => `telecaller-performance-${data.date_from}-to-${data.date_to}.csv`;

/** A 422 (a range rule) carries the API's sentence; anything else is a generic note. */
export const PERFORMANCE_UNAVAILABLE = "Telecaller performance is unavailable right now.";
export function performanceError(e: unknown): string {
  const { status, message } = (e ?? {}) as { status?: number; message?: unknown };
  return status === 422 && typeof message === "string" ? message : PERFORMANCE_UNAVAILABLE;
}
