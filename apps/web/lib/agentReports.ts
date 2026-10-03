import { isPage } from "@/lib/apiErrors";
import type { AgentReport, AgentReportOptions } from "@/lib/types";

// AGN-020 (DEC-SCOPE-063; spec §6.2-§6.3): the agency Reports page -- its tabs, the URL that holds the view, and the requests.

export const REPORTS_URL = "/api/v1/workflows/overseas/agent/crm/reports";
export const PAGE_SIZE = 50;
const MAX_OFFSET = 9_950; // the server's bound: paging stops where a 10,000-row export would

export type FilterKey = "member" | "country" | "university" | "intake" | "status";
export type ReportKey = "students" | "applications" | "universities" | "countries" | "intakes" | "staff" | "enrollments" | "commission";
export type ReportTab = { key: ReportKey; label: string; heading: string; description: string; filters: FilterKey[]; list: boolean; masterOnly: boolean };
export type ReportState = { report: ReportKey; from: string; to: string; filters: Partial<Record<FilterKey, string>>; offset: number };

// Spec §4: what each report counts, said under its heading. `filters` mirror the server's per-kind list (Masters only for `member`).
const TABS: ReportTab[] = [
  { key: "students", label: "Students", heading: "Students", description: "Agency student records created in the selected dates.", filters: ["member", "country", "status"], list: true, masterOnly: false },
  { key: "applications", label: "Applications", heading: "Applications", description: "Every application created in the selected dates, withdrawn ones included.", filters: ["member", "country", "university", "intake", "status"], list: true, masterOnly: false },
  { key: "universities", label: "Universities", heading: "Applications by university", description: "Applications created in the selected dates; withdrawn applications are not counted as applications.", filters: ["member", "country"], list: false, masterOnly: false },
  { key: "countries", label: "Countries", heading: "Applications by country", description: "Applications created in the selected dates; withdrawn applications are not counted as applications.", filters: ["member"], list: false, masterOnly: false },
  { key: "intakes", label: "Intakes", heading: "Applications by intake", description: "Intakes are read as month and year; anything else is grouped as Unstructured.", filters: ["member", "country"], list: false, masterOnly: false },
  { key: "staff", label: "Staff performance", heading: "Staff performance", description: "Each staff member's assigned students and their applications created in the selected dates.", filters: [], list: false, masterOnly: true },
  { key: "enrollments", label: "Enrollments", heading: "Enrollments", description: "Confirmed enrollments by enrollment date.", filters: ["member", "country", "university"], list: true, masterOnly: false },
  { key: "commission", label: "Commission", heading: "Commission report", description: "", filters: [], list: false, masterOnly: true },
];

// Which `options` list feeds each filter's control.
export const OPTION_LIST: Record<FilterKey, keyof AgentReportOptions> = { member: "members", country: "countries", university: "universities", intake: "intakes", status: "statuses" };
export const FILTER_LABEL: Record<FilterKey, string> = { member: "Staff member", country: "Country", university: "University", intake: "Intake", status: "Status" };

/** Masters (and a legacy agent with no membership, as AGN-014 treats one) get every tab. Staff never get Staff performance or
 *  Commission, and never the staff-member filter (the server refuses it: they only ever see their own students). */
export function tabsFor(memberRole: "master" | "staff" | null | undefined): ReportTab[] {
  if (memberRole !== "staff") return TABS;
  return TABS.filter((t) => !t.masterOnly).map((t) => ({ ...t, filters: t.filters.filter((f) => f !== "member") }));
}

const YYYY_MM_DD = /^\d{4}-\d{2}-\d{2}$/;

/** The view held in the address: only well-formed dates and the filters the chosen report offers survive (QA14-06 precedent). */
export function readState(search: string, tabs: ReportTab[]): ReportState {
  const params = new URLSearchParams(search);
  const tab = tabs.find((t) => t.key === params.get("report")) ?? tabs[0];
  const date = (key: string) => (YYYY_MM_DD.test(params.get(key) ?? "") ? (params.get(key) as string) : "");
  const filters: ReportState["filters"] = {};
  for (const key of tab.filters) {
    const value = params.get(key);
    if (value) filters[key] = value;
  }
  const offset = Number(params.get("offset"));
  const usable = tab.list && Number.isInteger(offset) && offset > 0 && offset <= MAX_OFFSET; // the server refuses beyond it (422)
  return { report: tab.key, from: date("from"), to: date("to"), filters, offset: usable ? offset : 0 };
}

/** replaceState: no history entry, no navigation; refresh, Back and a shared link keep the view. */
export function writeState(state: ReportState): void {
  const params = new URLSearchParams({ report: state.report });
  if (state.from) params.set("from", state.from);
  if (state.to) params.set("to", state.to);
  for (const [key, value] of Object.entries(state.filters)) if (value) params.set(key, value);
  if (state.offset) params.set("offset", String(state.offset));
  window.history.replaceState(window.history.state, "", `${window.location.pathname}?${params}`);
}

function filterParams(state: ReportState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.from) params.set("date_from", state.from);
  if (state.to) params.set("date_to", state.to);
  for (const [key, value] of Object.entries(state.filters)) if (value) params.set(key, value);
  return params;
}

export function reportQuery(state: ReportState): string {
  const params = filterParams(state);
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(state.offset));
  return `?${params}`;
}

export function csvUrl(state: ReportState): string {
  const query = filterParams(state).toString();
  return `${REPORTS_URL}/${state.report}.csv${query ? `?${query}` : ""}`;
}

export function csvFilename(kind: string, from: string, to: string): string {
  return `agency-${kind}-${from || "all"}-to-${to || "all"}.csv`;
}

// A 200 is only trusted if it has the report's shape: a proxy login page or an empty body must not crash the panel.
export function isAgentReport(data: unknown): data is AgentReport {
  if (!isPage(data)) return false; // also rules out null and non-objects
  const d = data as Partial<AgentReport>;
  return Array.isArray(d.columns) && typeof d.options === "object" && d.options !== null && typeof d.kind === "string";
}
