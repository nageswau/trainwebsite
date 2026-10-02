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

export function csvFilename(from: string, to: string): string {
  return `agency-commissions-${from || "all"}-to-${to || "all"}.csv`;
}

// A 200 is only trusted if it has the report's shape: a proxy login page or an empty body must not crash the panel.
export function isReport(data: unknown): data is CommissionReport {
  if (!data || typeof data !== "object" || Array.isArray(data)) return false;
  const record = data as Record<string, unknown>;
  return ["totals", "by_status", "by_university", "by_country", "by_intake"].every((key) => Array.isArray(record[key]));
}
