// pob-029 (DEC-SCOPE-437, API §12MD): placement outcome reports. The API computes every figure (services/placement_outcomes.py) and
// decides who reads it and whether the money columns are shown; these helpers shape the URL and the words. A null rate is "—", never 0%.
import { dayParam } from "@/lib/telecallerMetrics";

export const GROUPS = [
  { key: "company", label: "Company" }, { key: "vendor", label: "Vendor" }, { key: "role", label: "Role" },
  { key: "source", label: "Source" }, { key: "recruiter", label: "Recruiter" }, { key: "po", label: "Placement officer" },
] as const;
export type GroupKey = (typeof GROUPS)[number]["key"];
export type Figures = Record<string, number | string | null>;
export type OutcomeRow = { key: string | null; label: string; figures: Figures };
export type Funnel = {
  requirements: number; submissions: number; interviews: number; offers: number; offers_accepted: number; offers_declined: number;
  requirement_to_submission: number | null; submission_to_interview: number | null; interview_to_offer: number | null; offer_acceptance: number | null;
};
export type DrillRow = {
  id: string; status: string; status_label: string; candidate: { id: string; code: string; name: string };
  requirement: { id: string; code: string; title: string }; company: { id: string; name: string }; vendor: { id: string; name: string } | null;
  role: string; recruiter: string | null; po_owner: string | null; source: string | null; accepted_at: string; joined_on: string | null;
  dropout_on: string | null; early_dropout: boolean; client_rating: number | null; candidate_rating: number | null; fee: string | null;
};
export type Outcomes = {
  date_from: string; date_to: string; group_by: GroupKey; group_label: string; filters: Record<string, string>; revenue_visible: boolean;
  columns: { key: string; label: string }[]; totals: Figures; items: OutcomeRow[]; funnel: Funnel; placements: DrillRow[]; placements_total: number;
};
export type OutcomeParams = { from?: string; to?: string; group_by?: GroupKey; company?: string; vendor?: string; recruiter?: string; po?: string; source?: string };

export const OUTCOMES_URL = "/api/v1/recruiter/reports/placement-outcomes";
export const OUTCOMES_PATH = "/recruiter/manager/placement-outcomes";
export const FILTERS = ["company", "vendor", "recruiter", "po", "source"] as const;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PERCENT = new Set(["joining_rate"]);
const DAYS = new Set(["time_to_fill_days"]);
const RATINGS = new Set(["client_rating", "candidate_rating"]);
const MONEY = new Set(["fee_generated", "invoiced", "collected", "outstanding"]);

/** Only well-formed values reach the API, so its only 422s are the range rules, which carry a sentence to show. */
export function outcomeParams(raw: Record<string, string | undefined>): OutcomeParams {
  const params: OutcomeParams = { from: dayParam(raw.from), to: dayParam(raw.to) };
  if (GROUPS.some((g) => g.key === raw.group_by)) params.group_by = raw.group_by as GroupKey;
  for (const key of FILTERS) if (raw[key] && UUID.test(raw[key]!)) params[key] = raw[key];
  return params;
}

export function outcomeQuery(params: OutcomeParams): string {
  const query = new URLSearchParams(Object.entries(params).filter((entry): entry is [string, string] => !!entry[1])).toString();
  return query ? `?${query}` : "";
}

const inr = (value: string) => `₹${Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function formatFigure(key: string, value: number | string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (MONEY.has(key)) return inr(String(value));
  if (PERCENT.has(key)) return `${Number(value).toFixed(1)}%`;
  if (DAYS.has(key)) return `${Number(value).toFixed(1)} d`;
  if (RATINGS.has(key)) return Number(value).toFixed(1);
  return typeof value === "number" ? value.toLocaleString("en-IN") : value;
}

export const rateText = (rate: number | null) => (rate === null ? "—" : `${rate.toFixed(1)}%`);

/** The export carries the report's own period, grouping and filters, so the file is the table on screen. */
export function exportUrl(data: Outcomes): string {
  return `${OUTCOMES_URL}.csv${outcomeQuery({ from: data.date_from, to: data.date_to, group_by: data.group_by, ...data.filters })}`;
}
export const exportFilename = (data: Outcomes) => `placement-outcomes-by-${data.group_by}-${data.date_from}-to-${data.date_to}.csv`;

/** A group row's drill-down: the same period with that group as a filter (company, vendor, recruiter, PO and source have ids). */
export function drillHref(data: Outcomes, row: OutcomeRow): string | null {
  if (!row.key || !(FILTERS as readonly string[]).includes(data.group_by)) return null;
  return OUTCOMES_PATH + outcomeQuery({ from: data.date_from, to: data.date_to, group_by: data.group_by, ...data.filters, [data.group_by]: row.key });
}

export const OUTCOMES_UNAVAILABLE = "Placement outcome reports are unavailable right now.";
export function outcomesError(e: unknown): string {
  const { status, message } = (e ?? {}) as { status?: number; message?: unknown };
  return status === 422 && typeof message === "string" ? message : OUTCOMES_UNAVAILABLE;
}
