// mgmt-033 (spec DD1-DD14): GET /management/drill/{chain} -- one level of a revenue chain below the chosen path, or the record at its end.
// The API decides access (finance tier), every figure and every name; this file only reads and builds addresses. The path lives in the
// address (`path=<key>,<key>`, `none` = the unattributed row), so refresh, back and shared links keep it.
export const DRILL_HOME = "/management/drill";
export const DRILL_API = "/api/v1/management/drill";
export const PAGE_SIZE = 25;
export const DRILL_CHAINS = ["abroad", "it", "recruitment"] as const;
export const DRILL_LABEL: Record<DrillChain, string> = { abroad: "Abroad Education revenue", it: "IT Training revenue", recruitment: "Recruitment revenue" };
const MAX_DEPTH = 7; // the abroad chain, the longest

export type DrillChain = (typeof DRILL_CHAINS)[number];
export type Period = "month" | "year";
export type DrillCrumb = { level: string; level_label: string; key: string; name: string };
export type DrillRow = { key: string; name: string; amount: string; count: number; latest: string };
export type DrillRecord = {
  source: string; id: string; entry_date: string; amount: string; currency: string; description: string;
  details: { label: string; value: string }[];
  outcomes: { title: string; items: { name: string; detail: string | null; status: string }[] } | null;
}; // prettier-ignore
export type Drill = {
  chain: DrillChain; chain_label: string; month: string; period: Period; label: string; start: string; end: string;
  total: string; count: number; breadcrumbs: DrillCrumb[]; level: { key: string; label: string } | null;
  rows: DrillRow[]; total_rows: number; limit: number; offset: number; record: DrillRecord | null;
}; // prettier-ignore

export type Range = { month: string; period: Period };
export type DrillQuery = Range & { path: string[]; page: number };

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const KEY = /^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|none)$/i;
type Search = Record<string, string | string[] | undefined>;

export function isDrillChain(chain: string): chain is DrillChain {
  return (DRILL_CHAINS as readonly string[]).includes(chain);
}

function text(search: Search, key: string): string {
  const value = search[key];
  return typeof value === "string" ? value : "";
}

/** The page's address. A malformed month, period or page falls back to the API's default; a malformed path is dropped whole. */
export function drillQuery(search: Search): DrillQuery {
  const month = text(search, "month");
  const keys = text(search, "path") ? text(search, "path").split(",") : [];
  const path = keys.length <= MAX_DEPTH && keys.every((key) => KEY.test(key)) ? keys : [];
  const page = /^[1-9]\d{0,5}$/.test(text(search, "page")) ? Number(text(search, "page")) : 1;
  return { month: MONTH.test(month) ? month : "", period: search.period === "year" ? "year" : "month", path, page };
}

function params({ month, period }: Range, path: string[]): URLSearchParams {
  const out = new URLSearchParams({ ...(month ? { month } : {}), period });
  if (path.length) out.set("path", path.join(","));
  return out;
}

export function drillUrl(chain: DrillChain, query: DrillQuery): string {
  const out = params(query, query.path);
  out.set("limit", String(PAGE_SIZE));
  out.set("offset", String((query.page - 1) * PAGE_SIZE));
  return `${DRILL_API}/${chain}?${out}`;
}

/** The drill-down page at `path` (page `page`) for the same period. */
export function drillHref(chain: DrillChain, range: Range, path: string[], page = 1): string {
  const out = params(range, path);
  if (page > 1) out.set("page", String(page));
  return `${DRILL_HOME}/${chain}?${out}`;
}
