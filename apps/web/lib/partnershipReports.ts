// upc-031 (DEC-SCOPE-171, spec §5): the five partnership reports -- types, tabs and URLs. Every figure, column label and Total row comes
// from the API (services/partnership_reports.py), so the screen and the CSV always agree; the browser only lays them out.

export type PartnershipReportKind = "pipeline" | "expected" | "performance" | "agreements" | "targets";
export type PartnershipReportColumn = { key: string; label: string; numeric: boolean };
export type PartnershipReportRow = Record<string, string | number | null>;
export type PartnershipReport = {
  kind: PartnershipReportKind; title: string; as_of: string; filters: Record<string, string>; columns: PartnershipReportColumn[];
  items: PartnershipReportRow[]; totals: PartnershipReportRow | null; total: number; truncated: boolean; notes: string[];
};

export const REPORTS_PATH = "/partnership/reports";
export const REPORTS_URL = "/api/v1/partnership/reports";
export const REPORT_READERS = new Set(["partnership_manager", "partnership_head", "super_admin"]); // RP2

// RP1, in the backlog's order.
export const REPORT_TABS: { key: PartnershipReportKind; label: string }[] = [
  { key: "pipeline", label: "Pipeline by Country" }, { key: "expected", label: "Expected Partnerships" },
  { key: "performance", label: "University Performance" }, { key: "agreements", label: "Agreements Expiring" },
  { key: "targets", label: "Targets vs Actual" },
];

const FILTERS = ["window", "from", "to", "month"] as const;
export type PartnershipReportParams = Partial<Record<(typeof FILTERS)[number], string>>;
export const REPORT_FILTERS: Record<PartnershipReportKind, readonly (typeof FILTERS)[number][]> = {
  pipeline: [], expected: ["window"], performance: ["from", "to"], agreements: [], targets: ["month"],
};
// upc-023 EX9's windows.
export const WINDOW_OPTIONS = [
  { value: "all", label: "Every expected date" }, { value: "this_month", label: "This month" }, { value: "next_month", label: "Next month" },
  { value: "this_quarter", label: "This quarter" }, { value: "undated", label: "No expected date" },
];
export const SUMMARIES: Record<PartnershipReportKind, string> = {
  pipeline: "Active universities in your scope by country and partnership group, as on the dashboard.",
  expected: "Universities not yet signed with their expected agreement date and probability; the Total row's Weighted figure is the forecast.",
  performance: "The student funnel per university for a period, ranked by enrolments then applications, as on University Performance.",
  agreements: "Signed or active agreements that expire within 90 days, soonest first.",
  targets: "Each manager's monthly targets against what was achieved; the Total row is the team.",
};

export const reportKind = (raw: string | undefined): PartnershipReportKind => REPORT_TABS.find((t) => t.key === raw)?.key ?? "pipeline";

/** The page's own filters, from the address (anything else, or a repeated value, is ignored). */
export function reportParams(search: Record<string, string | string[] | undefined>): PartnershipReportParams {
  return Object.fromEntries(FILTERS.flatMap((key) => (typeof search[key] === "string" && search[key] ? [[key, search[key]]] : [])));
}

/** "?window=…" -- only the kind's own, non-empty filters. */
export function reportQuery(kind: PartnershipReportKind, params: PartnershipReportParams): string {
  const query = new URLSearchParams();
  for (const key of REPORT_FILTERS[kind]) if (params[key]) query.set(key, params[key]!);
  const text = query.toString();
  return text ? `?${text}` : "";
}

export const reportUrl = (kind: PartnershipReportKind, params: PartnershipReportParams) => `${REPORTS_URL}/${kind}${reportQuery(kind, params)}`;
export const csvUrl = (kind: PartnershipReportKind, params: PartnershipReportParams) => `${REPORTS_URL}/${kind}.csv${reportQuery(kind, params)}`;
// Each report has its own filters, so a tab opens the report with its defaults.
export const tabHref = (kind: PartnershipReportKind) => `${REPORTS_PATH}?report=${kind}`;
