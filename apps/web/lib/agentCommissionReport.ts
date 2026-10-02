// AGN-014 (DEC-SCOPE-051): the agency commission report's shape and URLs, shared by the panel and its tests. Mirrors
// CommissionReportOut (apps/api/app/schemas.py); the server remains the authority.

export const REPORT_URL = "/api/v1/workflows/overseas/agent/commissions/report";
export const CSV_URL = `${REPORT_URL}.csv`;

export type ReportGroup = { currency: string; count: number; amount: number };
export type CommissionReport = {
  date_from: string | null;
  date_to: string | null;
  totals: ReportGroup[];
  by_status: (ReportGroup & { status: string })[];
  by_university: (ReportGroup & { university: string; country: string })[];
  by_country: (ReportGroup & { country: string })[];
  by_intake: (ReportGroup & { intake: string })[];
};

export const STATUS_LABELS: Record<string, string> = {
  estimated: "Estimated",
  eligible: "Eligible",
  claimed: "Claimed",
  payout_pending: "Payout pending",
  paid: "Paid",
};

export function reportQuery(from: string, to: string): string {
  const params = new URLSearchParams();
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);
  const query = params.toString();
  return query ? `?${query}` : "";
}

// Browser QA14-06: the applied range lives in the page address (?from=&to=), so refresh, Back and a shared link keep it. Only
// well-formed YYYY-MM-DD values are read back; anything else means "no bound".
const YYYY_MM_DD = /^\d{4}-\d{2}-\d{2}$/;

export function readRange(search: string): { from: string; to: string } {
  const params = new URLSearchParams(search);
  const pick = (key: string) => {
    const value = params.get(key) ?? "";
    return YYYY_MM_DD.test(value) ? value : "";
  };
  return { from: pick("from"), to: pick("to") };
}

export function writeRange(range: { from: string; to: string }): void {
  const params = new URLSearchParams(window.location.search);
  for (const key of ["from", "to"] as const) {
    if (range[key]) params.set(key, range[key]);
    else params.delete(key);
  }
  const query = params.toString();
  // replaceState keeps Next's history entry state; no new entry, no navigation.
  window.history.replaceState(window.history.state, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
}

export function csvFilename(from: string, to: string): string {
  return `agency-commissions-${from || "all"}-to-${to || "all"}.csv`;
}

// A 200 is only trusted if it has the report's shape: a proxy login page or an empty body must not crash the panel.
export function isReport(data: unknown): data is CommissionReport {
  if (!data || typeof data !== "object" || Array.isArray(data)) return false;
  const record = data as Record<string, unknown>;
  return ["totals", "by_status", "by_university", "by_country", "by_intake"].every((key) => Array.isArray(record[key]));
}
