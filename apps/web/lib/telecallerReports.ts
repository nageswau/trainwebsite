// tel-024 (DEC-SCOPE-109): the five Telecaller CRM management reports -- types, tabs and URLs. Every figure, column label and option
// comes from the API (services/telecaller_reports.py); the browser only lays them out, so the screen and the CSV always agree.

export type ReportKind =
  | "source" | "product" | "telecaller" | "handover" | "campaign" | "lost" | "counselor" | "date" | "follow_ups" | "pending_follow_ups";
export type ReportColumn = { key: string; label: string };
export type ReportRow = Record<string, string | number>;
export type ReportOptions = {
  teams: string[];
  sources: { key: string; label: string }[];
  products: { id: string; name: string }[];
  campaigns: { id: string; name: string }[];
};
export type TelecallerReport = {
  kind: ReportKind; title: string; date_from: string; date_to: string;
  columns: ReportColumn[]; items: ReportRow[]; totals: ReportRow; options: ReportOptions;
};

const FILTERS = ["date_from", "date_to", "team", "product_id", "campaign_id", "source", "group"] as const;
const LEAD_FILTERS = new Set<string>(["product_id", "campaign_id", "source"]); // the telecaller report is per actor, not per lead
export type ReportParams = Partial<Record<(typeof FILTERS)[number], string>>;

// EVID-019 §21, in the source's order.
export const REPORT_TABS: { key: ReportKind; label: string }[] = [
  { key: "source", label: "Lead Source" }, { key: "product", label: "Course" }, { key: "telecaller", label: "Telecaller" },
  { key: "handover", label: "Counselor Handover" }, { key: "campaign", label: "Campaign" },
  { key: "lost", label: "Lost Reasons" }, // ccrm-006 (D9)
  // nehn-013 (DEC-SCOPE-300)
  { key: "counselor", label: "Counselor" }, { key: "date", label: "Date-wise" },
  { key: "follow_ups", label: "Follow-up Status" }, { key: "pending_follow_ups", label: "Pending Follow-ups" },
];
// nehn-013 R6: the date-wise report's periods (the API refuses anything else with a 422).
export const GROUPS = [{ value: "day", label: "Day" }, { value: "week", label: "Week" }, { value: "month", label: "Month" }];
export const TEAM_LABEL: Record<string, string> = { it: "IT", overseas: "Overseas" };
export const REPORTS_URL = "/api/v1/telecaller/reports";

export const reportKind = (raw: string | undefined): ReportKind => REPORT_TABS.find((t) => t.key === raw)?.key ?? "source";

/** The page's own filters, from the address (anything else, or a repeated value, is ignored). */
export function reportParams(search: Record<string, string | string[] | undefined>): ReportParams {
  return Object.fromEntries(FILTERS.flatMap((key) => (typeof search[key] === "string" && search[key] ? [[key, search[key]]] : [])));
}

/** "?date_from=…&team=…" -- known, non-empty filters only; the telecaller report drops the lead filters, and only the date-wise
 * report takes a grouping. */
export function reportQuery(kind: ReportKind, params: Record<string, string | undefined>): string {
  const query = new URLSearchParams();
  for (const key of FILTERS) {
    const value = params[key];
    if (value && !(kind === "telecaller" && LEAD_FILTERS.has(key)) && !(key === "group" && kind !== "date")) query.set(key, value);
  }
  const text = query.toString();
  return text ? `?${text}` : "";
}

export const reportUrl = (kind: ReportKind, params: ReportParams) => `${REPORTS_URL}/${kind}${reportQuery(kind, params)}`;
export const csvUrl = (kind: ReportKind, params: ReportParams) => `${REPORTS_URL}/${kind}.csv${reportQuery(kind, params)}`;

/** A tab keeps every filter in the address, so going back to a lead report restores them. */
export function tabHref(basePath: string, kind: ReportKind, params: ReportParams): string {
  const query = new URLSearchParams({ report: kind });
  for (const key of FILTERS) if (params[key]) query.set(key, params[key]!);
  return `${basePath}?${query.toString()}`;
}
