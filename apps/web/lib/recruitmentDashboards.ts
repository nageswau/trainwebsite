// hrc-033 (DEC-SCOPE-415, API §12LI): the five operational recruitment dashboards. The API decides access, scope, every figure and its
// definition (services/recruitment_dashboards.py); this file only reads and builds addresses, so refresh, back and shared links keep the state.
import { isCalendarDate } from "@/lib/formatDate";

export const DASHBOARDS_PATH = "/recruiter/recruitment-dashboards";
export const DASHBOARDS_API = "/api/v1/recruiter/recruitment-dashboards";
export const PAGE_SIZE = 25;
export const BOARD_TABS = [
  { key: "funnel", label: "Funnel" }, { key: "vacancy", label: "Vacancy" }, { key: "recruiter", label: "Recruiter" },
  { key: "officer", label: "Placement officer" }, { key: "interview", label: "Interview" },
] as const; // prettier-ignore
export type BoardKey = (typeof BOARD_TABS)[number]["key"];

export type Figure = { key: string; label: string; definition: string; value: number };
export type Option = { id: string; label: string };
export type Board = {
  board: BoardKey; label: string; note: string; owner_label: string; date_from: string | null; date_to: string | null; can_download: boolean;
  filters: { owner: string | null; employer: string | null; job: string | null };
  sections: { key: string; label: string; figures: Figure[] }[];
  options: { owners: Option[]; employers: Option[]; jobs: Option[] };
}; // prettier-ignore
export type DrillColumn = { key: string; label: string; type: "text" | "number" | "date" | "datetime" };
export type DrillRow = { id: string; href: string | null } & Record<string, string | number | null>;
export type Drill = { figure: { key: string; label: string; definition: string }; total: number; limit: number; offset: number; columns: DrillColumn[]; items: DrillRow[] };
export type DashboardQuery = { from: string; to: string; owner: string; employer: string; job: string; drill: string; offset: number };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const FIGURE_KEY = /^[a-z0-9_]{1,40}$/;

export const isBoard = (value: string): value is BoardKey => BOARD_TABS.some((tab) => tab.key === value);

/** The address as a query: a malformed or repeated value is dropped, so the API only ever answers to well-formed filters. */
export function dashboardQuery(search: Record<string, string | string[] | undefined>): DashboardQuery {
  const text = (key: string) => {
    const value = search[key];
    return typeof value === "string" ? value : "";
  };
  const day = (key: string) => (isCalendarDate(text(key)) ? text(key) : "");
  const id = (key: string) => (UUID.test(text(key)) ? text(key) : "");
  const offset = Number.parseInt(text("offset"), 10);
  return { from: day("from"), to: day("to"), owner: id("owner"), employer: id("employer"), job: id("job"), drill: FIGURE_KEY.test(text("drill")) ? text("drill") : "", offset: offset > 0 ? offset : 0 };
}

function filterParams(q: DashboardQuery): URLSearchParams {
  const params = new URLSearchParams();
  for (const key of ["from", "to", "owner", "employer", "job"] as const) if (q[key]) params.set(key, q[key]);
  return params;
}

const withQuery = (path: string, params: URLSearchParams) => (params.size ? `${path}?${params}` : path);

export const boardUrl = (board: BoardKey, q: DashboardQuery) => withQuery(`${DASHBOARDS_API}/${board}`, filterParams(q));
export const exportUrl = (board: BoardKey, q: DashboardQuery) => withQuery(`${DASHBOARDS_API}/${board}.csv`, filterParams(q));

export function drillUrl(board: BoardKey, q: DashboardQuery): string {
  const params = filterParams(q);
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(q.offset));
  return withQuery(`${DASHBOARDS_API}/${board}/drill/${q.drill}`, params);
}

/** The page's own address; a chosen figure scrolls to its records. */
export function pageHref(board: BoardKey, q: DashboardQuery): string {
  const params = filterParams(q);
  if (q.drill) params.set("drill", q.drill);
  if (q.drill && q.offset) params.set("offset", String(q.offset));
  return withQuery(`${DASHBOARDS_PATH}/${board}`, params) + (q.drill ? "#records" : "");
}

export function dashboardError(e: unknown): string {
  return e instanceof Error && e.message ? e.message : "This dashboard is unavailable right now. Please try again.";
}
